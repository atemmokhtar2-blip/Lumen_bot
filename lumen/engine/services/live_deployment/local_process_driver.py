"""
Local Process Driver — install deps robustly and run the bot process for real.

Uses LiveRunner install stack (preemptive conflict fix, venv/target fallback).
Separate install log vs run log so crash reasons are not buried under pip output.
"""

from __future__ import annotations

import logging
import os
import signal
import subprocess
import sys
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

_log = logging.getLogger("engine.live_deployment.local_process")
_RUNNING: Dict[str, dict] = {}


def _apply_resource_limits() -> None:
    """Apply resource limits to the child process (best-effort).

    LocalProcessDriver is a **fallback when Docker is unavailable**. Prefer Docker
    (memory/cpu/pids/cgroup isolation). These rlimits still reduce damage from
    runaway or malicious generated code (spin loops, fork bombs), but must remain
    high enough for a real Telegram bot:

      - python-telegram-bot / httpx / asyncio start worker threads
      - RLIMIT_NPROC=16 caused RuntimeError: can't start new thread (NetworkError)
      - RLIMIT_NOFILE=64 was too tight for concurrent HTTP sockets

    Env overrides (soft=hard, never raised above current hard limit):
      TBE_LOCAL_RLIMIT_CPU, TBE_LOCAL_RLIMIT_AS_MB, TBE_LOCAL_RLIMIT_NOFILE,
      TBE_LOCAL_RLIMIT_NPROC, TBE_LOCAL_RLIMIT_FSIZE_MB
    """
    try:
        import resource

        def _clamp_set(limit: int, soft: int, hard: int | None = None) -> None:
            """Set rlimit without exceeding the current hard ceiling."""
            if hard is None:
                hard = soft
            try:
                _cur_soft, cur_hard = resource.getrlimit(limit)
            except (ValueError, OSError):
                return
            try:
                if cur_hard != resource.RLIM_INFINITY and cur_hard >= 0:
                    hard = min(int(hard), int(cur_hard))
                soft = min(int(soft), int(hard) if hard != resource.RLIM_INFINITY else int(soft))
                if soft < 0:
                    return
                resource.setrlimit(limit, (soft, hard if hard != resource.RLIM_INFINITY else soft))
            except (ValueError, OSError) as exc:
                _log.debug("rlimit %s not applied: %s", limit, exc)

        # CPU seconds — long enough for install probe + polling session
        cpu = int(os.environ.get("TBE_LOCAL_RLIMIT_CPU", "600"))
        _clamp_set(resource.RLIMIT_CPU, cpu, cpu)

        # Address space — PTB + deps need more than 128 MiB under load
        mem_mb = int(os.environ.get("TBE_LOCAL_RLIMIT_AS_MB", "384"))
        mem = max(128, mem_mb) * 1024 * 1024
        _clamp_set(resource.RLIMIT_AS, mem, mem)

        # Open files / sockets — 64 was starving httpx connection pools
        nofile = int(os.environ.get("TBE_LOCAL_RLIMIT_NOFILE", "256"))
        _clamp_set(resource.RLIMIT_NOFILE, max(64, nofile), max(64, nofile))

        # Processes + threads (Linux counts threads toward NPROC for the UID).
        # Default 128: enough for PTB network stack; still blocks fork bombs.
        # Previous default 16 → immediate crash: can't start new thread.
        nproc = int(os.environ.get("TBE_LOCAL_RLIMIT_NPROC", "128"))
        _clamp_set(resource.RLIMIT_NPROC, max(32, nproc), max(32, nproc))

        _clamp_set(resource.RLIMIT_CORE, 0, 0)

        fsize_mb = int(os.environ.get("TBE_LOCAL_RLIMIT_FSIZE_MB", "64"))
        fsize = max(16, fsize_mb) * 1024 * 1024
        _clamp_set(resource.RLIMIT_FSIZE, fsize, fsize)
    except Exception as exc:
        _log.debug("resource limits not applied: %s", exc)


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



def _local_process_allowed() -> bool:
    """Local subprocess only when isolation policy allow_local (dev/single-tenant only)."""
    try:
        from lumen.engine.services.isolation_policy import decide_isolation, is_multi_tenant
        if is_multi_tenant():
            return False
        return bool(decide_isolation().allow_local)
    except Exception:
        return False


class LocalProcessDriver(DeploymentProvider):
    name = "local_process"

    def deploy(
        self,
        project_path: str,
        *,
        env_vars: Optional[Dict[str, str]] = None,
        service_name: str = "generated-bot",
    ) -> DeploymentStatus:
        """Host-process fallback with RLIMIT sandbox when Docker is unavailable."""
        if not _local_process_allowed():
            return DeploymentStatus(
                provider=self.name,
                status=DEPLOY_FAILED,
                message="LocalProcessDriver disabled by isolation policy.",
            )
        from lumen.engine.services.isolation_policy import assert_local_process_allowed
        assert_local_process_allowed()

        path = Path(project_path).resolve()
        if not path.is_dir():
            return DeploymentStatus(
                provider=self.name,
                status=DEPLOY_FAILED,
                message=f"Project path not found: {project_path}",
            )
        try:
            from lumen.engine.services.safe_fs import assert_no_symlinks_in_path
            assert_no_symlinks_in_path(path)
        except Exception as _sym_exc:
            return DeploymentStatus(
                provider=self.name,
                status=DEPLOY_FAILED,
                message=f"project_path_symlink_forbidden:{type(_sym_exc).__name__}",
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
                message="BOT_TOKEN missing — cannot start the bot process.",
            )

        dep_id = f"local-{uuid.uuid4().hex[:10]}"
        install_log = path / f".deploy_{dep_id}.install.log"
        run_log = path / f".deploy_{dep_id}.run.log"

        self._stop_by_project(str(path))

        try:
            python_bin, mode, isolation = self._ensure_runtime_and_deps(path, install_log)
        except Exception as e:
            tail = self._read_log(install_log, limit=15)
            return DeploymentStatus(
                provider=self.name,
                deployment_id=dep_id,
                status=DEPLOY_FAILED,
                message=(
                    f"Dependency install failed: {type(e).__name__}: {e}. "
                    f"Log: {' | '.join(tail[-5:]) if tail else 'empty'}"
                ),
            )

        from lumen.engine.services.live_runner.source_fix import (
            repair_project_sources,
            discover_token_env_names,
            syntax_check_entry,
        )
        repair_notes = repair_project_sources(path)
        ok_syn, syn_err = syntax_check_entry(entry)
        if not ok_syn:
            return DeploymentStatus(
                provider=self.name,
                deployment_id=dep_id,
                status=DEPLOY_FAILED,
                message=f"SyntaxError in {entry.name}: {syn_err}. repair={repair_notes[:3]}",
            )

        from lumen.engine.services.user_sandbox import clean_child_env, write_token_file
        token_path = write_token_file(path, bot_token)
        child_env = clean_child_env(bot_token, token_file=token_path)
        # Only inject names the project actually references (capped)
        for key in discover_token_env_names(path)[:6]:
            if key not in child_env:
                child_env[key] = bot_token
        child_env.pop("PORT", None)
        if mode.startswith("target"):
            pp = child_env.get("PYTHONPATH", "")
            child_env["PYTHONPATH"] = str(isolation) + (os.pathsep + pp if pp else "")

        try:
            log_f = open(run_log, "w", encoding="utf-8")
            log_f.write(f"--- starting {entry.name} with {python_bin} (mode={mode}) ---\n")
            log_f.flush()
            proc = subprocess.Popen(
                [python_bin, str(entry)],
                cwd=str(path),
                env=child_env,
                stdout=log_f,
                stderr=subprocess.STDOUT,
                start_new_session=True,
                preexec_fn=_apply_resource_limits,
            )
        except Exception as e:
            return DeploymentStatus(
                provider=self.name,
                deployment_id=dep_id,
                status=DEPLOY_FAILED,
                message=f"Failed to start process: {type(e).__name__}: {e}",
            )

        time.sleep(2.5)
        rc = proc.poll()
        if rc is not None:
            tail = self._read_log(run_log, limit=60)
            useful = [
                ln for ln in tail
                if any(k in ln for k in ("Error", "Traceback", "Exception", "error", "Missing", "module"))
            ]
            show = useful[-12:] if useful else tail[-12:]
            run_text = "\n".join(tail)
            try:
                log_f.close()
            except Exception:
                pass
            healed = self._heal_and_restart(
                path=path,
                entry=entry,
                bot_token=bot_token,
                service_name=service_name,
                dep_id=dep_id,
                run_log=run_log,
                install_log=install_log,
                run_text=run_text,
                max_rounds=2,
            )
            if healed.status == DEPLOY_RUNNING:
                return healed
            # Root-cause hint for the common RLIMIT_NPROC trap
            joined = " ".join(show) if show else ""
            nproc_hint = ""
            if (
                "can't start new thread" in joined
                or "cant start new thread" in joined.lower()
                or "start new thread" in joined
            ):
                nproc_hint = (
                    " Root cause: process/thread limit too low for python-telegram-bot "
                    "(RLIMIT_NPROC). Platform defaults were raised; override with "
                    "TBE_LOCAL_RLIMIT_NPROC=128+ if still failing. Prefer Docker isolation."
                )
            return DeploymentStatus(
                provider=self.name,
                deployment_id=dep_id,
                status=DEPLOY_FAILED,
                message=(
                    f"Bot process exited immediately (code={rc}). "
                    f"Heal: {healed.message}. "
                    f"Run log: {' | '.join(show) if show else 'empty'}.{nproc_hint}"
                ),
            )

        _RUNNING[dep_id] = {
            "proc": proc,
            "project_path": str(path),
            "entry": str(entry),
            "log_path": str(run_log),
            "install_log": str(install_log),
            "python": python_bin,
            "started_at": time.time(),
            "log_file": log_f,
        }

        return DeploymentStatus(
            provider=self.name,
            deployment_id=dep_id,
            service_id=service_name,
            status=DEPLOY_RUNNING,
            message=f"Bot process running (pid={proc.pid}, entry={entry.name}, mode={mode}).",
            dry_run=False,
        )

    def status(self, deployment_id: str) -> DeploymentStatus:
        info = _RUNNING.get(deployment_id)
        if not info:
            return DeploymentStatus(
                provider=self.name,
                deployment_id=deployment_id,
                status=DEPLOY_STOPPED,
                message="Unknown or stopped deployment.",
            )
        proc: subprocess.Popen = info["proc"]
        rc = proc.poll()
        if rc is None:
            return DeploymentStatus(
                provider=self.name,
                deployment_id=deployment_id,
                status=DEPLOY_RUNNING,
                message=f"Running (pid={proc.pid}).",
            )
        return DeploymentStatus(
            provider=self.name,
            deployment_id=deployment_id,
            status=DEPLOY_FAILED if rc != 0 else DEPLOY_STOPPED,
            message=f"Process exited with code={rc}.",
        )

    def stop(self, deployment_id: str) -> DeploymentStatus:
        info = _RUNNING.pop(deployment_id, None)
        if not info:
            return DeploymentStatus(
                provider=self.name,
                deployment_id=deployment_id,
                status=DEPLOY_STOPPED,
                message="Already stopped.",
            )
        self._kill_proc(info)
        return DeploymentStatus(
            provider=self.name,
            deployment_id=deployment_id,
            status=DEPLOY_STOPPED,
            message="Bot process stopped.",
        )

    def restart(self, deployment_id: str, *, bot_token: str = "",
                project_path: str = "") -> DeploymentStatus:
        """Smart restart: stop the old process, then start a fresh one with
        the *same* project_path + bot_token so the edited code runs immediately.

        This is the real "kill old → start new" path.  The caller (engine
        layer) supplies the token it retrieved from the sealed SecretsManager
        and the project_path from the deployment registry.  We stop the old
        process first (graceful SIGTERM → SIGKILL fallback), then deploy a
        brand-new process that picks up the updated source files on disk.
        """
        # 1) stop the old deployment (graceful)
        info = _RUNNING.get(deployment_id)
        resolved_path = project_path or (info.get("project_path") if info else "")
        self.stop(deployment_id)

        if not bot_token or not resolved_path:
            return DeploymentStatus(
                provider=self.name,
                deployment_id=deployment_id,
                status=DEPLOY_STOPPED,
                message=(
                    "Old process stopped. Cannot restart: bot_token/project_path "
                    "not supplied (restart-by-project needs both)."
                ),
            )

        # 2) deploy a fresh process with the updated code + same token
        new_status = self.deploy(
            resolved_path,
            env_vars={"BOT_TOKEN": bot_token},
            service_name=Path(resolved_path).name[:40] or "generated-bot",
        )
        if new_status.status == DEPLOY_RUNNING:
            new_status.message = f"Restarted (old killed, new started). {new_status.message}"
        return new_status

    def logs(self, deployment_id: str, *, limit: int = 50) -> List[str]:
        info = _RUNNING.get(deployment_id)
        if not info:
            return [f"No logs for {deployment_id}"]
        return self._read_log(Path(info["log_path"]), limit=limit)

    def _ensure_runtime_and_deps(self, project_path: Path, install_log: Path) -> tuple[str, str, Path]:
        """Reuse LiveRunner robust installer."""
        from lumen.engine.services.live_runner.parts.runtime_bootstrap import (
            _ensure_runtime,
            _find_requirements,
        )
        from lumen.engine.services.live_runner.parts.requirements_pip import (
            _pip_install,
            _preflight_ensure_deps,
        )

        pre_notes: list = []
        try:
            pre_notes = _preflight_ensure_deps(project_path)
        except Exception as e:
            pre_notes = [f"preflight_error:{type(e).__name__}"]

        # Package Reality pre-host check (warn only; never blocks install)
        pkg_notes: list = []
        try:
            from lumen.engine.services.package_reality import (
                assess_repo_packages,
                recommend_upgrades,
            )
            preport = assess_repo_packages(project_path)
            pkg_notes.append(
                f"package_health={preport.health_score:.2f} "
                f"outdated={preport.outdated_count} major_lag={preport.major_lag_count} "
                f"yanked={preport.yanked_count}"
            )
            for rec in recommend_upgrades(preport)[:8]:
                pkg_notes.append(
                    f"upgrade:{rec.name}:{rec.kind}:{'auto' if rec.auto_applicable else 'manual'}"
                )
        except Exception as e:
            pkg_notes.append(f"package_reality_skip:{type(e).__name__}")

        py, mode, isolation, note = _ensure_runtime(project_path)
        req = _find_requirements(project_path)
        ok, log, warns = _pip_install(py, req, project_path, mode, isolation)
        install_log.write_text(
            f"mode={mode}\nnote={note}\npreflight={pre_notes}\npackage_reality={pkg_notes}\nwarns={warns}\n\n{log}",
            encoding="utf-8",
        )
        if not ok:
            raise RuntimeError(
                "pip install failed after auto-fix attempts. "
                + (log[-500:].replace("\n", " ") if log else "")
            )
        # If venv mode still has no usable pip path issues — py is already selected
        return py, mode, isolation


    def _heal_and_restart(
        self,
        path: Path,
        entry: Path,
        bot_token: str,
        service_name: str,
        dep_id: str,
        run_log: Path,
        install_log: Path,
        run_text: str,
        max_rounds: int = 2,
    ) -> DeploymentStatus:
        """Error Intelligence decides packages → pip install → restart process."""
        # Auto-heal pip install is OFF by default (package injection / log poisoning).
        # Enable only in trusted dev with TBE_ALLOW_AUTO_HEAL=1.
        import os as _os
        if (_os.environ.get("TBE_ALLOW_AUTO_HEAL") or "0").strip().lower() not in {
            "1", "true", "yes", "on",
        }:
            return DeploymentStatus(
                provider=self.name,
                deployment_id=dep_id,
                status=DEPLOY_FAILED,
                message="auto-heal disabled (set TBE_ALLOW_AUTO_HEAL=1 only in trusted dev)",
            )

        from lumen.engine.services.error_intelligence import analyze_logs
        from lumen.engine.services.live_runner.parts.runtime_bootstrap import (
            _ensure_runtime,
        )
        from lumen.engine.services.live_runner.parts.requirements_pip import (
            _ensure_packages_in_requirements,
            _pip_install_packages_direct,
            _module_to_package,
        )
        try:
            from lumen.engine.services.live_runner.parts.requirements_pip import (
                _resolve_missing_via_source,
            )
        except ImportError:
            def _resolve_missing_via_source(*a, **k):
                return []
        from lumen.engine.services.live_runner.source_fix import (
            discover_token_env_names,
        )

        last_msg = ""
        for round_i in range(max_rounds):
            install_txt = ""
            if install_log.exists():
                try:
                    install_txt = install_log.read_text(encoding="utf-8", errors="ignore")
                except Exception:
                    pass
            contract = analyze_logs(
                run_log=run_text,
                install_log=install_txt,
                phase="run",
            )
            packages: list[str] = list(contract.heal_packages or [])
            for sm in _resolve_missing_via_source(path, run_text):
                pkg = _module_to_package(sm)
                if pkg and pkg not in packages:
                    packages.append(pkg)
            if not packages and contract.primary and contract.primary.suggested_package:
                packages = [contract.primary.suggested_package]
            try:
                from lumen.engine.services.prod_hard_locks import auto_heal_pip_allowed
                if not auto_heal_pip_allowed():
                    packages = []
            except Exception:
                packages = []
            if not packages:
                import re as _re
                for m in _re.finditer(r"No module named ['\"]([^'\"]+)['\"]", run_text or ""):
                    full = m.group(1)
                    pkg = _module_to_package(full) or _module_to_package(full.split(".")[0])
                    if pkg and pkg not in packages:
                        packages.append(pkg)
            if not packages:
                summary = (
                    contract.primary.summary_ar if contract.primary else (run_text or "")[:300]
                )
                return DeploymentStatus(
                    provider=self.name,
                    deployment_id=dep_id,
                    status=DEPLOY_FAILED,
                    message=f"Bot process exited; not healable. {summary}",
                )

            _ensure_packages_in_requirements(path, packages)
            py, mode, isolation, _note = _ensure_runtime(path)
            ok_d, dlog = _pip_install_packages_direct(py, packages, path, mode, isolation)
            try:
                with open(install_log, "a", encoding="utf-8") as f:
                    f.write(f"\n--- host heal round {round_i + 1}: {packages} ok={ok_d} ---\n{dlog}\n")
            except Exception:
                pass
            if not ok_d:
                last_msg = f"heal pip failed for {packages}"
                continue

            from lumen.engine.services.user_sandbox import clean_child_env
            child_env = clean_child_env(bot_token)
            for key in discover_token_env_names(path):
                child_env[key] = bot_token
            child_env.pop("PORT", None)
            if mode.startswith("target"):
                pp = child_env.get("PYTHONPATH", "")
                child_env["PYTHONPATH"] = str(isolation) + (os.pathsep + pp if pp else "")

            log_f = open(run_log, "a", encoding="utf-8")
            log_f.write(f"\n--- host heal restart round {round_i + 1} packages={packages} ---\n")
            log_f.flush()
            proc = subprocess.Popen(
                [py, str(entry)],
                cwd=str(path),
                env=child_env,
                stdout=log_f,
                stderr=subprocess.STDOUT,
                start_new_session=True,
                preexec_fn=_apply_resource_limits,
            )
            time.sleep(2.5)
            rc = proc.poll()
            if rc is None:
                _RUNNING[dep_id] = {
                    "proc": proc,
                    "project_path": str(path),
                    "entry": str(entry),
                    "log_path": str(run_log),
                    "install_log": str(install_log),
                    "python": py,
                    "started_at": time.time(),
                    "log_file": log_f,
                }
                return DeploymentStatus(
                    provider=self.name,
                    deployment_id=dep_id,
                    service_id=service_name,
                    status=DEPLOY_RUNNING,
                    message=(
                        f"Bot process running after heal "
                        f"(pid={proc.pid}, packages={packages}, entry={entry.name})."
                    ),
                    dry_run=False,
                )
            run_text = "\n".join(self._read_log(run_log, limit=80))
            last_msg = f"still exiting code={rc} after heal {packages}"
            try:
                log_f.close()
            except Exception:
                pass

        return DeploymentStatus(
            provider=self.name,
            deployment_id=dep_id,
            status=DEPLOY_FAILED,
            message=last_msg or "heal exhausted",
        )

    def _stop_by_project(self, project_path: str) -> None:
        to_stop = [
            did for did, info in list(_RUNNING.items())
            if info.get("project_path") == project_path
        ]
        for did in to_stop:
            info = _RUNNING.pop(did, None)
            if info:
                self._kill_proc(info)

    @staticmethod
    def _kill_proc(info: dict) -> None:
        proc: subprocess.Popen = info["proc"]
        try:
            if proc.poll() is None:
                try:
                    os.killpg(proc.pid, signal.SIGTERM)
                except Exception:
                    proc.terminate()
                try:
                    proc.wait(timeout=8)
                except Exception:
                    try:
                        os.killpg(proc.pid, signal.SIGKILL)
                    except Exception:
                        proc.kill()
        finally:
            lf = info.get("log_file")
            if lf:
                try:
                    lf.close()
                except Exception:
                    pass

    @staticmethod
    def _read_log(log_path: Path, limit: int = 50) -> List[str]:
        if not log_path.exists():
            return []
        try:
            lines = log_path.read_text(encoding="utf-8", errors="replace").splitlines()
            return lines[-limit:]
        except Exception:
            return []
