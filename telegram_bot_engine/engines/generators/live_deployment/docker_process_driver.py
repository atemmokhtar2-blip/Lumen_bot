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
Falls back gracefully when Docker is unavailable (local driver with limits).
"""

from __future__ import annotations

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
        path = Path(project_path).resolve()
        if not path.is_dir():
            return DeploymentStatus(
                provider=self.name,
                status=DEPLOY_FAILED,
                message=f"Project path not found: {project_path}",
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

        # Ensure image is present (pull if needed, best-effort)
        pull_err = self._ensure_image()
        if pull_err:
            return DeploymentStatus(
                provider=self.name,
                deployment_id=dep_id,
                status=DEPLOY_FAILED,
                message=f"Docker image pull failed: {pull_err}",
            )

        rel_entry = entry.relative_to(path).as_posix()
        # Install deps into /tmp/deps (writable tmpfs) so rootfs can stay read-only.
        # Project is mounted at /app.
        install_and_run = (
            "set -e; "
            "cd /app; "
            "mkdir -p /tmp/deps; "
            "if [ -f requirements.txt ]; then "
            "  pip install --no-cache-dir -q --target /tmp/deps -r requirements.txt || true; "
            "fi; "
            "export PYTHONPATH=/tmp/deps:${PYTHONPATH:-}; "
            f"exec python -u {rel_entry}"
        )

        cmd = [
            "docker", "run",
            "-d",
            "--name", cname,
            "--label", f"tbe.project={path}",
            "--label", f"tbe.user={user_seg}",
            "--label", "tbe.managed=1",
            "--label", "tbe.isolation=strong",
            # Never auto-restart a potentially malicious / broken bot
            "--restart", "no",
            # Resource limits (tight defaults protect the host)
            f"--memory={_MEMORY}",
            f"--memory-swap={_MEMORY}",  # no extra swap
            f"--cpus={_CPUS}",
            f"--pids-limit={_PIDS}",
            "--ulimit", "nproc=32:32",
            "--ulimit", "nofile=128:128",
            # Log size limit so runaway logging cannot fill disk
            "--log-driver", "json-file",
            "--log-opt", "max-size=2m",
            "--log-opt", "max-file=2",
            # Security hardening
            "--security-opt", "no-new-privileges:true",
            "--cap-drop", "ALL",
            "--read-only",
            # Writable spaces only where needed (deps + temp)
            # /tmp must allow exec for pip wheels / native extensions during install
            "--tmpfs", "/tmp:rw,exec,nosuid,nodev,size=96m",
            "--tmpfs", "/var/tmp:rw,noexec,nosuid,nodev,size=16m",
            # Network: allow outbound (Telegram API) but no published ports
            "--network", "bridge",
            # Mount ONLY this user's project directory (sandbox path)
            "-v", f"{path}:/app:rw",
            "-w", "/app",
            # Run as non-root when possible (best-effort; some images lack the uid)
            "--user", _RUN_AS_USER,
            # Minimal env — never pass host AI keys or host bot token
            "-e", "PYTHONUNBUFFERED=1",
            "-e", "PYTHONDONTWRITEBYTECODE=1",
            "-e", "TBE_SANDBOX=docker",
            "-e", "TBE_ISOLATED=1",
            "-e", "HOME=/tmp",
            "-e", "PYTHONPATH=/tmp/deps",
            "-e", f"BOT_TOKEN={bot_token}",
            "-e", f"TELEGRAM_BOT_TOKEN={bot_token}",
            "-e", f"TOKEN={bot_token}",
            self._image,
            "sh", "-c", install_and_run,
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

        # If --user caused failure (image has no matching uid), retry without it
        if proc.returncode != 0 and "--user" in cmd:
            err_txt = ((proc.stderr or "") + (proc.stdout or "")).lower()
            if any(k in err_txt for k in ("unable to find user", "unknown user", "no such user", "invalid user")):
                _log.info("Docker --user %s failed; retrying without non-root user", _RUN_AS_USER)
                cleaned: List[str] = []
                skip_next = False
                for c in cmd:
                    if skip_next:
                        skip_next = False
                        continue
                    if c == "--user":
                        skip_next = True
                        continue
                    cleaned.append(c)
                try:
                    proc = subprocess.run(
                        cleaned,
                        capture_output=True,
                        text=True,
                        timeout=60,
                        check=False,
                    )
                except Exception as e:
                    return DeploymentStatus(
                        provider=self.name,
                        deployment_id=dep_id,
                        status=DEPLOY_FAILED,
                        message=f"docker run (fallback) failed: {type(e).__name__}: {e}",
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
