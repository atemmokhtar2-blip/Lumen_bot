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
    """Apply strict resource limits to the child process (best-effort).

    LocalProcessDriver is a **dev fallback only**. Prefer Docker
    (memory/cpu/pids/cgroup isolation). These rlimits reduce damage from
    runaway or malicious generated code (infinite loops, fork bombs):
    CPU time, address space, open files, process count, and file size.
    """
    try:
        import resource
        # CPU wall-ish: 120s hard (prevents pure spin loops monopolizing a core forever)
        cpu = int(os.environ.get("TBE_LOCAL_RLIMIT_CPU", "120"))
        resource.setrlimit(resource.RLIMIT_CPU, (cpu, cpu))
        # Address space ~128 MiB default
        mem = int(os.environ.get("TBE_LOCAL_RLIMIT_AS_MB", "128")) * 1024 * 1024
        try:
            resource.setrlimit(resource.RLIMIT_AS, (mem, mem))
        except (ValueError, OSError):
            pass
        # Open files
        resource.setrlimit(resource.RLIMIT_NOFILE, (64, 64))
        # Max processes/threads — low to blunt fork bombs
        try:
            resource.setrlimit(resource.RLIMIT_NPROC, (16, 16))
        except (ValueError, OSError):
            pass
        # Core dumps off
        try:
            resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
        except (ValueError, OSError):
            pass
        # Max file size written by the child (~32 MiB)
        try:
            resource.setrlimit(resource.RLIMIT_FSIZE, (32 * 1024 * 1024, 32 * 1024 * 1024))
        except (ValueError, OSError):
            pass
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
    """Local subprocess hosting is dev-only and opt-in."""
    import os
    flag = (os.environ.get("TBE_ALLOW_LOCAL_PROCESS") or "0").strip().lower()
    if flag not in {"1", "true", "yes", "on"}:
        return False
    env = (os.environ.get("ENVIRONMENT") or os.environ.get("TBE_ENV") or "").strip().lower()
    # Even with the flag, refuse when multi-tenant unless explicitly overridden
    multi = (os.environ.get("TBE_MULTI_TENANT") or "1").strip().lower()
    if multi in {"1", "true", "yes", "on"} and env not in {"dev", "development", "local", "test"}:
        return False
    return True


class LocalProcessDriver(DeploymentProvider):
    name = "local_process"

    def deploy(
        self,
        project_path: str,
        *,
        env_vars: Optional[Dict[str, str]] = None,
        service_name: str = "generated-bot",
    ) -> DeploymentStatus:
        if not _local_process_allowed():
            return DeploymentStatus(
                provider=self.name,
                status=DEPLOY_FAILED,
                message=(
                    'LocalProcessDriver disabled. '
                    'Production must use Docker '
                    '(TBE_ALLOW_LOCAL_PROCESS only in ENVIRONMENT=dev).'
                ),
            )
        # Root gate: refuse to run untrusted code without explicit local-dev opt-in
        from telegram_bot_engine.services.isolation_policy import assert_local_process_allowed
        assert_local_process_allowed()

        path = Path(project_path).resolve()
        if not path.is_dir():
            return DeploymentStatus(
                provider=self.name,
                status=DEPLOY_FAILED,
                message=f"Project path not found: {project_path}",
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

        from telegram_bot_engine.services.live_runner.source_fix import (
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

        from telegram_bot_engine.services.user_sandbox import clean_child_env, write_token_file
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
            return DeploymentStatus(
                provider=self.name,
                deployment_id=dep_id,
                status=DEPLOY_FAILED,
                message=(
                    f"Bot process exited immediately (code={rc}). "
                    f"Heal: {healed.message}. "
                    f"Run log: {' | '.join(show) if show else 'empty'}"
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

    def restart(self, deployment_id: str) -> DeploymentStatus:
        self.stop(deployment_id)
        return DeploymentStatus(
            provider=self.name,
            deployment_id=deployment_id,
            status=DEPLOY_STOPPED,
            message="Stopped. Call deploy() again with BOT_TOKEN to restart.",
        )

    def logs(self, deployment_id: str, *, limit: int = 50) -> List[str]:
        info = _RUNNING.get(deployment_id)
        if not info:
            return [f"No logs for {deployment_id}"]
        return self._read_log(Path(info["log_path"]), limit=limit)

    def _ensure_runtime_and_deps(self, project_path: Path, install_log: Path) -> tuple[str, str, Path]:
        """Reuse LiveRunner robust installer."""
        from telegram_bot_engine.services.live_runner.service import (
            _ensure_runtime,
            _find_requirements,
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
            from telegram_bot_engine.services.package_reality import (
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

        from telegram_bot_engine.services.error_intelligence import analyze_logs
        from telegram_bot_engine.services.live_runner.service import (
            _ensure_runtime,
            _ensure_packages_in_requirements,
            _pip_install_packages_direct,
            _resolve_missing_via_source,
            _module_to_package,
        )
        from telegram_bot_engine.services.live_runner.source_fix import (
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

            from telegram_bot_engine.services.user_sandbox import clean_child_env
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
