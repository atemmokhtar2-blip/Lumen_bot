"""
Docker Process Driver — strong per-user isolation for generated bots.

Each user's bot runs in its own container with:
  - unique name (tbe-u{user_id}-{short_id})
  - memory / CPU / pids / ulimit limits
  - dropped ALL capabilities, no-new-privileges
  - read-only rootfs + constrained tmpfs
  - only the user's project directory mounted (scoped sandbox path)
  - minimal env (bot token only — never host TELEGRAM_BOT_TOKEN or AI keys)
  - outbound network only (bridge, no published ports)
  - non-root user when possible, restart=no, log size limits
  - labels for cleanup and ownership tracking

This layer protects the main generator bot from any generated user code.
Production path: build immutable image + run without host source bind-mount.
LocalProcessDriver is never used as a silent fallback from this module.
"""

from __future__ import annotations

def _cm_default_output_dir() -> str:
    try:
        from b2b_platform.paths import default_output_dir
        return default_output_dir()
    except Exception:
        from pathlib import Path as _P
        p = _P.home() / '.capability_maestro'
        p.mkdir(parents=True, exist_ok=True)
        return str(p)


import logging
import os
import re
import shutil
import subprocess
import time
import uuid
from pathlib import Path
from typing import Dict, List, Optional

from .deployment_provider import DeploymentProvider
from .report_data import (
    DEPLOY_FAILED,
    DEPLOY_RUNNING,
    DEPLOY_STOPPED,
    DeploymentStatus,
)

_log = logging.getLogger("engine.live_deployment.docker")

# Registry of running containers managed by this process
_RUNNING: Dict[str, dict] = {}

_DEFAULT_IMAGE = os.environ.get("TBE_DOCKER_IMAGE", "python:3.11-slim")
_MEMORY = os.environ.get("TBE_DOCKER_MEMORY", "192m")
_CPUS = os.environ.get("TBE_DOCKER_CPUS", "0.4")
_PIDS = os.environ.get("TBE_DOCKER_PIDS", "48")
_TIMEOUT_PULL = int(os.environ.get("TBE_DOCKER_PULL_TIMEOUT", "120"))
# Non-root UID/GID inside container (nobody-like). Image must have this user or we fall back.
_RUN_AS_USER = os.environ.get("TBE_DOCKER_USER", "65534:65534")



def _assert_sandbox_mount_path(project_path: Path) -> Path:
    """Refuse unsafe paths. Worker artifact workdirs are allowed under OUTPUT_DIR/artifacts."""
    path = project_path.resolve()
    if not path.is_dir():
        raise ValueError("project_path_not_a_directory")
    out = Path(os.environ.get("OUTPUT_DIR") or _cm_default_output_dir()).resolve()
    art = Path(os.environ.get("TBE_ARTIFACT_ROOT") or (out / "artifacts")).resolve()
    # Image-based deploy no longer bind-mounts source; still confine build context roots.
    under_out = False
    under_art = False
    try:
        path.relative_to(out)
        under_out = True
    except ValueError:
        pass
    try:
        path.relative_to(art)
        under_art = True
    except ValueError:
        pass
    worker = (os.environ.get("TBE_WORKER_BUILD") or "").strip().lower() in {"1", "true", "yes", "on"}
    if under_art and worker:
        return path
    if under_out and ("users" in path.parts or "artifacts" in path.parts):
        return path
    if under_out and worker:
        return path
    raise ValueError("project_path_outside_allowed_roots")


def docker_available() -> bool:
    """Return True if docker CLI is present and the daemon responds."""
    if not shutil.which("docker"):
        return False
    try:
        r = subprocess.run(
            ["docker", "info"],
            capture_output=True,
            text=True,
            timeout=8,
            check=False,
        )
        return r.returncode == 0
    except Exception:
        return False


def _safe_name(value: str, max_len: int = 40) -> str:
    s = re.sub(r"[^a-zA-Z0-9_.-]+", "-", (value or "").strip())[:max_len]
    return s.strip("-") or "x"


def _find_entry_point(project_path: Path) -> Optional[Path]:
    for name in ("main.py", "bot.py", "app.py", "run.py"):
        p = project_path / name
        if p.is_file():
            return p
    for c in project_path.glob("*/main.py"):
        return c
    for c in project_path.glob("*/bot.py"):
        return c
    return None


def _extract_user_id(project_path: Path) -> str:
    """Best-effort extract telegram user id from sandbox path layout.

    Supports both layouts:
      .../users/<user_id>/projects/<project_id>/
      .../users/<xx>/<yy>/<user_id>/projects/<project_id>/   (sharded)
    """
    parts = list(project_path.resolve().parts)
    try:
        if "users" in parts:
            idx = parts.index("users")
            # Prefer the last numeric segment after "users" that looks like a telegram id
            for i in range(idx + 1, min(idx + 5, len(parts))):
                seg = parts[i]
                if seg.isdigit() and len(seg) >= 5:
                    return _safe_name(seg, 24)
            # Fallback: first segment after users
            if idx + 1 < len(parts):
                return _safe_name(parts[idx + 1], 24)
    except Exception:
        pass
    return "anon"



def _assert_docker_host_policy() -> None:
    """Refuse insecure Docker API exposure patterns in multi-tenant production.

    Operators must not point DOCKER_HOST at an open TCP daemon without TLS.
    unix:///var/run/docker.sock is allowed only when TBE_ALLOW_DOCKER_SOCKET=1
    is set explicitly (still requires host hardening / rootless docker).
    """
    import os
    env = (os.getenv("ENVIRONMENT") or os.getenv("TBE_ENV") or "production").strip().lower()
    if env in {"dev", "development", "local", "test"}:
        return
    host = (os.getenv("DOCKER_HOST") or "").strip()
    if host.startswith("tcp://") and "tls" not in host.lower():
        # tcp without explicit TLS vars is dangerous
        if not (os.getenv("DOCKER_TLS_VERIFY") or "").strip():
            raise RuntimeError(
                "DOCKER_HOST tcp:// without DOCKER_TLS_VERIFY is forbidden in production"
            )
    sock_ok = (os.getenv("TBE_ALLOW_DOCKER_SOCKET") or "").strip().lower() in {"1", "true", "yes", "on"}
    if (not host or host.startswith("unix://")) and not sock_ok:
        # Default socket path is common; require explicit opt-in on multi-tenant hosts
        multi = (os.getenv("TBE_MULTI_TENANT") or "1").strip().lower() in {"1", "true", "yes", "on"}
        if multi:
            # Soft warning path was too weak — require opt-in flag for multi-tenant
            raise RuntimeError(
                "Multi-tenant production requires TBE_ALLOW_DOCKER_SOCKET=1 "
                "(acknowledge host docker.sock risk) or DOCKER_HOST with TLS"
            )


class DockerProcessDriver(DeploymentProvider):
    """Run generated bots inside isolated Docker containers (per user)."""

    name = "docker"

    def __init__(self) -> None:
        self._image = _DEFAULT_IMAGE

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def deploy(
        self,
        project_path: str,
        *,
        env_vars: Optional[Dict[str, str]] = None,
        service_name: str = "generated-bot",
    ) -> DeploymentStatus:
        # Reject shell metacharacters — docker argv is a list, but we still
        # refuse dangerous paths before any process is spawned.
        raw = str(project_path or "")
        if re.search(r"[;|&$`<>\\\n\r\0]", raw):
            return DeploymentStatus(
                provider=self.name,
                status=DEPLOY_FAILED,
                message="invalid_path_characters",
            )
        try:
            path = _assert_sandbox_mount_path(Path(raw))
        except ValueError as exc:
            return DeploymentStatus(
                provider=self.name,
                status=DEPLOY_FAILED,
                message=f"Project path rejected: {exc}",
            )

        if not docker_available():
            return DeploymentStatus(
                provider=self.name,
                status=DEPLOY_FAILED,
                message="Docker is not available on this host.",
            )

        entry = _find_entry_point(path)
        if entry is None:
            return DeploymentStatus(
                provider=self.name,
                status=DEPLOY_FAILED,
                message="No main.py / bot.py entry point found in project.",
            )

        env_vars = dict(env_vars or {})
        bot_token = (
            env_vars.get("BOT_TOKEN")
            or env_vars.get("TELEGRAM_BOT_TOKEN")
            or env_vars.get("TOKEN")
            or ""
        )
        if not bot_token:
            return DeploymentStatus(
                provider=self.name,
                status=DEPLOY_FAILED,
                message="BOT_TOKEN missing — cannot start the bot container.",
            )

        user_seg = _extract_user_id(path)
        short = uuid.uuid4().hex[:10]
        dep_id = f"docker-{user_seg}-{short}"
        cname = f"tbe-u{_safe_name(user_seg, 20)}-{short}"

        # Stop any previous container for the same project path
        self._stop_by_project(str(path))

        # --- Immutable image build (no host source bind-mount at runtime) ---
        try:
            from telegram_bot_engine.services.requirements_policy import sanitize_requirements_text
            req = path / "requirements.txt"
            if req.is_file():
                raw_req = req.read_text(encoding="utf-8", errors="ignore")
                cleaned, _warns = sanitize_requirements_text(raw_req)
                # Fail closed: never ship unsanitized requirements into the image.
                if (raw_req.strip() and not cleaned.strip()
                        and any(
                            ln.strip() and not ln.strip().startswith("#")
                            for ln in raw_req.splitlines()
                        )):
                    return DeploymentStatus(
                        provider=self.name,
                        deployment_id=dep_id,
                        status=DEPLOY_FAILED,
                        message="requirements_all_blocked_by_allowlist",
                    )
                req.write_text(cleaned, encoding="utf-8")
                if _warns:
                    _log.info("requirements sanitize warnings: %s", _warns[:8])
                from telegram_bot_engine.services.dependency_scanner import scan_requirements_file
                ok_s, errs_s, _ws = scan_requirements_file(req)
                if not ok_s:
                    return DeploymentStatus(
                        provider=self.name,
                        deployment_id=dep_id,
                        status=DEPLOY_FAILED,
                        message="dependency_scan_blocked:" + ";".join(errs_s[:12]),
                    )
        except Exception as _req_exc:
            _log.error("requirements sanitize failed — refusing deploy: %s", _req_exc)
            return DeploymentStatus(
                provider=self.name,
                deployment_id=dep_id,
                status=DEPLOY_FAILED,
                message=f"requirements_sanitize_failed:{type(_req_exc).__name__}",
            )

        # Multi-tenant: refuse default bridge — operator must set egress-limited network
        try:
            from telegram_bot_engine.services.isolation_policy import is_multi_tenant
            if is_multi_tenant() and not (os.environ.get("TBE_DOCKER_NETWORK") or "").strip():
                return DeploymentStatus(
                    provider=self.name,
                    deployment_id=dep_id,
                    status=DEPLOY_FAILED,
                    message=(
                        "TBE_DOCKER_NETWORK must be set in multi-tenant mode "
                        "(egress-limited docker network required; default bridge refused)"
                    ),
                )
        except Exception:
            pass

        from telegram_bot_engine.services.bot_image_builder import build_image
        ok_img, image_tag, build_log = build_image(
            path, user_id=user_seg, entry=entry.name, timeout=int(os.environ.get("TBE_DOCKER_BUILD_TIMEOUT", "600")),
        )
        if not ok_img:
            return DeploymentStatus(
                provider=self.name,
                deployment_id=dep_id,
                status=DEPLOY_FAILED,
                message=f"image build failed: {image_tag} | {(build_log or '')[-300:]}",
            )
        self._image = image_tag  # run THIS bot's image, not a shared base

        # Runtime: image-only (code baked in). No bind-mount of user source.
        # Writable tmp only; read-only rootfs.
        net = (os.environ.get("TBE_DOCKER_NETWORK") or "").strip()
        if not net:
            # Fail closed — never silently use default bridge in this path
            return DeploymentStatus(
                provider=self.name,
                deployment_id=dep_id,
                status=DEPLOY_FAILED,
                message="TBE_DOCKER_NETWORK is required (egress-limited network)",
            )
        try:
            from telegram_bot_engine.services.bot_image_builder import validate_image_tag
            image_tag = validate_image_tag(image_tag)
        except Exception as _tag_exc:
            return DeploymentStatus(
                provider=self.name,
                deployment_id=dep_id,
                status=DEPLOY_FAILED,
                message=f"invalid image tag: {_tag_exc}",
            )

        # Token via ephemeral env-file (not argv); file removed after docker run
        import tempfile
        env_file_path = None
        secret_path = None
        try:
            # Token validation: Telegram form digits:secret
            import re as _re
            if not _re.fullmatch(r"\d{6,12}:[A-Za-z0-9_-]{30,}", bot_token.strip()):
                return DeploymentStatus(
                    provider=self.name,
                    deployment_id=dep_id,
                    status=DEPLOY_FAILED,
                    message="bot token format rejected",
                )
            ef = tempfile.NamedTemporaryFile(
                mode="w",
                prefix="tbe_env_",
                suffix=".env",
                delete=False,
                encoding="utf-8",
            )
            env_file_path = ef.name
            # Only bot token keys — nothing from host environ
            ef.write(f"BOT_TOKEN={bot_token.strip()}\n")
            ef.write(f"TELEGRAM_BOT_TOKEN={bot_token.strip()}\n")
            ef.write("PYTHONUNBUFFERED=1\n")
            ef.write("PYTHONDONTWRITEBYTECODE=1\n")
            ef.write("TBE_SANDBOX=docker-image\n")
            ef.write("TBE_ISOLATED=1\n")
            ef.write("AWS_EC2_METADATA_DISABLED=true\n")
            ef.write("HOME=/tmp\n")
            ef.close()
            try:
                os.chmod(env_file_path, 0o600)
            except Exception:
                pass

            # Token also as read-only secret file (400) — reduces sole reliance on env
            secret_path = None
            try:
                sf = tempfile.NamedTemporaryFile(
                    mode="w",
                    prefix="tbe_tok_",
                    suffix=".secret",
                    delete=False,
                    encoding="utf-8",
                )
                secret_path = sf.name
                sf.write(bot_token.strip())
                sf.close()
                os.chmod(secret_path, 0o400)
            except Exception:
                secret_path = None

            cmd = [
                "docker", "run",
                "-d",
                "--name", cname,
                "--label", f"tbe.user={user_seg}",
                "--label", "tbe.managed=1",
                "--label", "tbe.isolation=image",
                "--restart", "no",
                f"--memory={_MEMORY}",
                f"--memory-swap={_MEMORY}",
                f"--cpus={_CPUS}",
                f"--pids-limit={_PIDS}",
                "--ulimit", "nproc=32:32",
                "--ulimit", "nofile=128:128",
                "--log-driver", "json-file",
                "--log-opt", "max-size=2m",
                "--log-opt", "max-file=2",
                "--security-opt", "no-new-privileges:true",
                "--cap-drop", "ALL",
                "--read-only",
                "--ipc", "none",
                "--tmpfs", "/tmp:rw,noexec,nosuid,nodev,size=64m",
                "--tmpfs", "/var/tmp:rw,noexec,nosuid,nodev,size=16m",
                "--network", net,
                "-w", "/app",
                "--user", "10001:10001",
                "--env-file", env_file_path,
                *([
                    "--mount", f"type=bind,source={secret_path},target=/run/secrets/bot_token,readonly",
                    "-e", "TBE_TOKEN_FILE=/run/secrets/bot_token",
                ] if secret_path else []),
                image_tag,
            ]

            try:
                proc = subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    timeout=60,
                    check=False,
                )
            except subprocess.TimeoutExpired:
                return DeploymentStatus(
                    provider=self.name,
                    deployment_id=dep_id,
                    status=DEPLOY_FAILED,
                    message="docker run timed out",
                )
            except Exception as e:
                return DeploymentStatus(
                    provider=self.name,
                    deployment_id=dep_id,
                    status=DEPLOY_FAILED,
                    message=f"docker run failed: {type(e).__name__}: {e}",
                )
        finally:
            if env_file_path:
                try:
                    with open(env_file_path, "w", encoding="utf-8") as _wf:
                        _wf.write(chr(0) * 64)
                    os.unlink(env_file_path)
                except Exception:
                    pass
            if secret_path:
                try:
                    with open(secret_path, "w", encoding="utf-8") as _sf:
                        _sf.write(chr(0) * 64)
                    os.unlink(secret_path)
                except Exception:
                    pass


        # NOTE: proc is assigned inside try; if env setup failed we returned early


        # NEVER fall back to root. Non-root is mandatory isolation.
        if proc.returncode != 0 and "--user" in cmd:
            err_txt = ((proc.stderr or "") + (proc.stdout or "")).lower()
            if any(k in err_txt for k in ("unable to find user", "unknown user", "no such user", "invalid user")):
                _log.error("Docker non-root user 10001 unavailable; refusing root fallback")
                return DeploymentStatus(
                    provider=self.name,
                    deployment_id=dep_id,
                    status=DEPLOY_FAILED,
                    message=(
                        "Image lacks non-root user 10001; refusing to run as root. "
                        "Image build should create botuser (uid 10001)."
                    ),
                )

        if proc.returncode != 0:
            err = (proc.stderr or proc.stdout or "").strip()[:400]
            return DeploymentStatus(
                provider=self.name,
                deployment_id=dep_id,
                status=DEPLOY_FAILED,
                message=f"docker run exited {proc.returncode}: {err}",
            )

        container_id = (proc.stdout or "").strip()[:64]
        time.sleep(2.5)

        # Check if still running
        st = self._inspect_running(cname)
        if not st:
            logs = self._docker_logs(cname, limit=40)
            self._force_rm(cname)
            useful = [ln for ln in logs if any(k in ln for k in ("Error", "Traceback", "Exception", "error"))]
            show = useful[-10:] if useful else logs[-10:]
            return DeploymentStatus(
                provider=self.name,
                deployment_id=dep_id,
                status=DEPLOY_FAILED,
                message=(
                    "Container exited immediately. "
                    + (" | ".join(show) if show else "no logs")
                )[:500],
            )

        _RUNNING[dep_id] = {
            "container": cname,
            "container_id": container_id,
            "project_path": str(path),
            "entry": str(entry),
            "user": user_seg,
            "started_at": time.time(),
        }

        try:
            from telegram_bot_engine.services.deployment_registry import get_deployment_registry
            get_deployment_registry().upsert({
                "deployment_id": dep_id,
                "user_id": int(user_seg) if str(user_seg).isdigit() else 0,
                "container_name": cname,
                "container_id": container_id,
                "image_tag": getattr(self, "_image", ""),
                "project_path": str(path),
                "status": "running",
            })
        except Exception as _reg_exc:
            _log.warning("deployment registry upsert failed: %s", _reg_exc)

        return DeploymentStatus(
            provider=self.name,
            deployment_id=dep_id,
            service_id=cname,
            status=DEPLOY_RUNNING,
            message=f"Bot running in isolated Docker container `{cname}` (user={user_seg}).",
        )

    def status(self, deployment_id: str) -> DeploymentStatus:
        info = _RUNNING.get(deployment_id)
        if not info:
            try:
                from telegram_bot_engine.services.deployment_registry import get_deployment_registry
                rec = get_deployment_registry().get(deployment_id)
                if rec:
                    info = {
                        "container": rec.get("container_name") or "",
                        "container_id": rec.get("container_id") or "",
                        "project_path": rec.get("project_path") or "",
                        "image": rec.get("image_tag") or "",
                    }
                    if info["container"]:
                        _RUNNING[deployment_id] = info
            except Exception:
                info = None
        if not info or not info.get("container"):
            return DeploymentStatus(
                provider=self.name,
                deployment_id=deployment_id,
                status=DEPLOY_STOPPED,
                message="Unknown or already cleaned deployment_id",
            )
        cname = info["container"]
        if self._inspect_running(cname):
            return DeploymentStatus(
                provider=self.name,
                deployment_id=deployment_id,
                service_id=cname,
                status=DEPLOY_RUNNING,
                message=f"Container `{cname}` is running.",
            )
        return DeploymentStatus(
            provider=self.name,
            deployment_id=deployment_id,
            service_id=cname,
            status=DEPLOY_STOPPED,
            message=f"Container `{cname}` is not running.",
        )

    def stop(self, deployment_id: str) -> DeploymentStatus:
        info = _RUNNING.pop(deployment_id, None)
        if not info:
            # try to find by label / name pattern
            return DeploymentStatus(
                provider=self.name,
                deployment_id=deployment_id,
                status=DEPLOY_STOPPED,
                message="Already stopped or unknown.",
            )
        cname = info["container"]
        self._force_rm(cname)
        return DeploymentStatus(
            provider=self.name,
            deployment_id=deployment_id,
            service_id=cname,
            status=DEPLOY_STOPPED,
            message=f"Stopped and removed container `{cname}`.",
        )

    def restart(self, deployment_id: str) -> DeploymentStatus:
        info = _RUNNING.get(deployment_id)
        if not info:
            return DeploymentStatus(
                provider=self.name,
                deployment_id=deployment_id,
                status=DEPLOY_FAILED,
                message="Cannot restart: unknown deployment_id",
            )
        path = info["project_path"]
        # Re-deploy with same path; token must be re-supplied by caller in practice.
        # We keep the old token only if still in env of previous — but we don't store it.
        return DeploymentStatus(
            provider=self.name,
            deployment_id=deployment_id,
            status=DEPLOY_FAILED,
            message="Restart requires re-providing the bot token via deploy().",
        )

    def logs(self, deployment_id: str, *, limit: int = 50) -> List[str]:
        info = _RUNNING.get(deployment_id)
        if not info:
            return []
        return self._docker_logs(info["container"], limit=limit)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _ensure_image(self) -> str:
        """Pull image if missing. Return error string or empty on success."""
        try:
            insp = subprocess.run(
                ["docker", "image", "inspect", self._image],
                capture_output=True,
                text=True,
                timeout=15,
                check=False,
            )
            if insp.returncode == 0:
                return ""
            pull = subprocess.run(
                ["docker", "pull", self._image],
                capture_output=True,
                text=True,
                timeout=_TIMEOUT_PULL,
                check=False,
            )
            if pull.returncode != 0:
                return (pull.stderr or pull.stdout or "pull failed")[:300]
            return ""
        except Exception as e:
            return f"{type(e).__name__}: {e}"

    def _inspect_running(self, cname: str) -> bool:
        try:
            r = subprocess.run(
                ["docker", "inspect", "-f", "{{.State.Running}}", cname],
                capture_output=True,
                text=True,
                timeout=10,
                check=False,
            )
            return r.returncode == 0 and "true" in (r.stdout or "").lower()
        except Exception:
            return False

    def _docker_logs(self, cname: str, *, limit: int = 50) -> List[str]:
        try:
            r = subprocess.run(
                ["docker", "logs", "--tail", str(limit), cname],
                capture_output=True,
                text=True,
                timeout=15,
                check=False,
            )
            out = (r.stdout or "") + (r.stderr or "")
            return [ln for ln in out.splitlines() if ln.strip()][-limit:]
        except Exception:
            return []

    def _force_rm(self, cname: str) -> None:
        try:
            subprocess.run(
                ["docker", "rm", "-f", cname],
                capture_output=True,
                text=True,
                timeout=20,
                check=False,
            )
        except Exception as e:
            _log.debug("docker rm failed for %s: %s", cname, e)

    def _stop_by_project(self, project_path: str) -> None:
        """Stop any managed container for this project path."""
        to_del = [
            did for did, info in list(_RUNNING.items())
            if info.get("project_path") == project_path
        ]
        for did in to_del:
            self.stop(did)

        # Also clean orphans by label (best-effort)
        try:
            r = subprocess.run(
                [
                    "docker", "ps", "-aq",
                    "--filter", f"label=tbe.project={project_path}",
                    "--filter", "label=tbe.managed=1",
                ],
                capture_output=True,
                text=True,
                timeout=15,
                check=False,
            )
            ids = [x.strip() for x in (r.stdout or "").splitlines() if x.strip()]
            for cid in ids:
                subprocess.run(
                    ["docker", "rm", "-f", cid],
                    capture_output=True,
                    timeout=15,
                    check=False,
                )
        except Exception:
            pass
