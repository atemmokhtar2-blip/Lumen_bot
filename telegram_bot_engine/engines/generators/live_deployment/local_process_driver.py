"""
Local Process Driver — runs the generated bot for real on this host.

1. Create a virtualenv inside the project (optional but preferred)
2. pip install -r requirements.txt
3. Start main.py / bot.py as a background process with BOT_TOKEN in env
4. Track PID for stop / restart / logs

Never logs the BOT_TOKEN value.
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

# Global registry of running bots (deployment_id → process info)
_RUNNING: Dict[str, dict] = {}


def _find_entry_point(project_path: Path) -> Optional[Path]:
    candidates = [
        project_path / "main.py",
        project_path / "bot.py",
        project_path / "app.py",
    ]
    for c in candidates:
        if c.is_file():
            return c
    # Nested common layouts
    for c in project_path.glob("*/main.py"):
        return c
    for c in project_path.glob("*/core/main.py"):
        return c
    return None


def _find_requirements(project_path: Path) -> Optional[Path]:
    for name in ("requirements.txt", "requirements-dev.txt"):
        p = project_path / name
        if p.is_file():
            return p
    return None


class LocalProcessDriver(DeploymentProvider):
    """Deploy by installing deps and running the bot process locally."""

    name = "local_process"

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

        entry = _find_entry_point(path)
        if entry is None:
            return DeploymentStatus(
                provider=self.name,
                status=DEPLOY_FAILED,
                message="No main.py / bot.py entry point found in project.",
            )

        env_vars = dict(env_vars or {})
        bot_token = env_vars.get("BOT_TOKEN", "")
        if not bot_token:
            return DeploymentStatus(
                provider=self.name,
                status=DEPLOY_FAILED,
                message="BOT_TOKEN missing — cannot start the bot process.",
            )

        dep_id = f"local-{uuid.uuid4().hex[:10]}"
        log_path = path / f".deploy_{dep_id}.log"

        # Stop any previous process for same project path
        self._stop_by_project(str(path))

        try:
            python_bin = self._ensure_venv_and_deps(path, log_path)
        except Exception as e:
            return DeploymentStatus(
                provider=self.name,
                deployment_id=dep_id,
                status=DEPLOY_FAILED,
                message=f"Dependency install failed: {type(e).__name__}: {e}",
            )

        # Build env for child (includes BOT_TOKEN — never logged)
        child_env = os.environ.copy()
        child_env["BOT_TOKEN"] = bot_token
        child_env["PYTHONUNBUFFERED"] = "1"
        # Avoid the child bot conflicting if it tries to bind same port
        child_env.pop("PORT", None)

        try:
            log_f = open(log_path, "a", encoding="utf-8")
            proc = subprocess.Popen(
                [python_bin, str(entry)],
                cwd=str(entry.parent if entry.parent != path else path),
                env=child_env,
                stdout=log_f,
                stderr=subprocess.STDOUT,
                start_new_session=True,
            )
        except Exception as e:
            return DeploymentStatus(
                provider=self.name,
                deployment_id=dep_id,
                status=DEPLOY_FAILED,
                message=f"Failed to start process: {type(e).__name__}: {e}",
            )

        # Brief wait to catch instant crashes
        time.sleep(2.0)
        rc = proc.poll()
        if rc is not None:
            tail = self._read_log(log_path, limit=30)
            return DeploymentStatus(
                provider=self.name,
                deployment_id=dep_id,
                status=DEPLOY_FAILED,
                message=(
                    f"Bot process exited immediately (code={rc}). "
                    f"Last log: {' | '.join(tail[-5:]) if tail else 'empty'}"
                ),
            )

        _RUNNING[dep_id] = {
            "proc": proc,
            "project_path": str(path),
            "entry": str(entry),
            "log_path": str(log_path),
            "python": python_bin,
            "started_at": time.time(),
            "log_file": log_f,
        }

        _log.info(
            "Bot process started",
            extra={
                "deployment_id": dep_id,
                "pid": proc.pid,
                "entry": str(entry.name),
            },
        )

        return DeploymentStatus(
            provider=self.name,
            deployment_id=dep_id,
            service_id=service_name,
            status=DEPLOY_RUNNING,
            message=f"Bot process running (pid={proc.pid}, entry={entry.name}).",
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
        info = _RUNNING.get(deployment_id)
        if not info:
            return DeploymentStatus(
                provider=self.name,
                deployment_id=deployment_id,
                status=DEPLOY_FAILED,
                message="Cannot restart: deployment not found.",
            )
        project = info["project_path"]
        # Token must be re-supplied via deploy(); restart without token is limited
        self.stop(deployment_id)
        return DeploymentStatus(
            provider=self.name,
            deployment_id=deployment_id,
            status=DEPLOY_STOPPED,
            message=(
                "Stopped previous process. Call deploy() again with BOT_TOKEN "
                "to restart."
            ),
        )

    def logs(self, deployment_id: str, *, limit: int = 50) -> List[str]:
        info = _RUNNING.get(deployment_id)
        if not info:
            return [f"No logs for {deployment_id}"]
        return self._read_log(Path(info["log_path"]), limit=limit)

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _ensure_venv_and_deps(self, project_path: Path, log_path: Path) -> str:
        """Create .venv if needed, pip install requirements, return python path."""
        venv_dir = project_path / ".venv"
        if sys.platform == "win32":
            python_bin = str(venv_dir / "Scripts" / "python.exe")
            pip_bin = str(venv_dir / "Scripts" / "pip.exe")
        else:
            python_bin = str(venv_dir / "bin" / "python")
            pip_bin = str(venv_dir / "bin" / "pip")

        if not Path(python_bin).exists():
            _log.info("Creating virtualenv", extra={"path": str(venv_dir)})
            subprocess.run(
                [sys.executable, "-m", "venv", str(venv_dir)],
                check=True,
                cwd=str(project_path),
                capture_output=True,
                timeout=120,
            )

        req = _find_requirements(project_path)
        if req is not None:
            _log.info("Installing requirements", extra={"file": req.name})
            with open(log_path, "a", encoding="utf-8") as lf:
                lf.write(f"\n--- pip install -r {req.name} ---\n")
                proc = subprocess.run(
                    [python_bin, "-m", "pip", "install", "--upgrade", "pip"],
                    cwd=str(project_path),
                    capture_output=True,
                    text=True,
                    timeout=180,
                )
                lf.write(proc.stdout or "")
                lf.write(proc.stderr or "")
                proc = subprocess.run(
                    [
                        python_bin,
                        "-m",
                        "pip",
                        "install",
                        "-r",
                        str(req),
                    ],
                    cwd=str(project_path),
                    capture_output=True,
                    text=True,
                    timeout=300,
                )
                lf.write(proc.stdout or "")
                lf.write(proc.stderr or "")
                if proc.returncode != 0:
                    raise RuntimeError(
                        f"pip install failed (code={proc.returncode}). "
                        f"See deploy log."
                    )
        else:
            # Minimal installs for common frameworks if no requirements file
            _log.info("No requirements.txt — installing common telegram deps")
            subprocess.run(
                [
                    python_bin,
                    "-m",
                    "pip",
                    "install",
                    "aiogram>=3.4",
                    "python-telegram-bot>=21",
                    "python-dotenv>=1.0",
                ],
                cwd=str(project_path),
                capture_output=True,
                timeout=300,
                check=False,
            )

        return python_bin

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
