"""DeploymentProvider backed by sandbox_runtime.

Production path: Firecracker only (via select_sandbox_backend).
Dev may use weaker backends when TBE_SANDBOX_BACKEND is set explicitly.
LocalProcess is not used here.
"""
from __future__ import annotations

import logging
from typing import Dict, List, Optional

from .deployment_provider import DeploymentProvider
from .report_data import (
    DEPLOY_FAILED,
    DEPLOY_RUNNING,
    DEPLOY_STOPPED,
    DeploymentStatus,
)

logger = logging.getLogger(__name__)


def _user_id_from_env(env_vars: Optional[Dict[str, str]]) -> int:
    if not env_vars:
        return 0
    for key in ("TBE_USER_ID", "USER_ID", "LUMEN_USER_ID"):
        raw = (env_vars.get(key) or "").strip()
        if raw.isdigit():
            return int(raw)
    return 0


def _token_from_env(env_vars: Optional[Dict[str, str]]) -> str:
    if not env_vars:
        return ""
    return (
        (env_vars.get("TELEGRAM_BOT_TOKEN") or env_vars.get("BOT_TOKEN") or "").strip()
    )


class SandboxProcessDriver(DeploymentProvider):
    """Thin adapter: DeploymentProvider API → sandbox_runtime.start_sandboxed_bot."""

    name = "sandbox_runtime"

    def deploy(
        self,
        project_path: str,
        *,
        env_vars: Optional[Dict[str, str]] = None,
        service_name: str = "generated-bot",
    ) -> DeploymentStatus:
        token = _token_from_env(env_vars)
        if not token:
            return DeploymentStatus(
                status=DEPLOY_FAILED,
                deployment_id="",
                message="sandbox_deploy_missing_bot_token",
            )
        try:
            from lumen.engine.services.sandbox_runtime import start_sandboxed_bot

            backend, handle = start_sandboxed_bot(
                project_path=str(project_path),
                bot_token=token,
                user_id=_user_id_from_env(env_vars),
                service_name=service_name or "generated-bot",
                env_vars=dict(env_vars or {}),
            )
        except Exception as exc:
            return DeploymentStatus(
                status=DEPLOY_FAILED,
                deployment_id="",
                message=f"sandbox_deploy_error:{type(exc).__name__}:{exc}"[:500],
            )
        dep = handle.deployment_id or ""
        if handle.ok and str(handle.status).lower() in {"running", "starting"}:
            return DeploymentStatus(
                status=DEPLOY_RUNNING,
                deployment_id=dep,
                message=f"{backend.name}:{handle.message}"[:500],
            )
        return DeploymentStatus(
            status=DEPLOY_FAILED,
            deployment_id=dep,
            message=f"{backend.name}:{handle.message}"[:500],
        )

    def status(self, deployment_id: str) -> DeploymentStatus:
        dep = (deployment_id or "").strip()
        if not dep:
            return DeploymentStatus(status=DEPLOY_STOPPED, deployment_id="", message="empty_id")
        try:
            if dep.startswith("fc-"):
                from lumen.engine.services.sandbox_runtime.firecracker_backend import (
                    FirecrackerSandboxBackend,
                )
                h = FirecrackerSandboxBackend().status(dep)
            else:
                from lumen.engine.services.sandbox_runtime import select_sandbox_backend

                backend, _ = select_sandbox_backend(require_available=False)
                h = backend.status(dep)
            st = str(h.status).lower()
            if st == "running":
                return DeploymentStatus(status=DEPLOY_RUNNING, deployment_id=dep, message=h.message)
            if st in {"failed", "error"}:
                return DeploymentStatus(status=DEPLOY_FAILED, deployment_id=dep, message=h.message)
            return DeploymentStatus(status=DEPLOY_STOPPED, deployment_id=dep, message=h.message)
        except Exception as exc:
            return DeploymentStatus(
                status=DEPLOY_FAILED,
                deployment_id=dep,
                message=f"status_error:{type(exc).__name__}",
            )

    def stop(self, deployment_id: str) -> DeploymentStatus:
        dep = (deployment_id or "").strip()
        if not dep:
            return DeploymentStatus(status=DEPLOY_STOPPED, deployment_id="", message="empty_id")
        try:
            if dep.startswith("fc-"):
                from lumen.engine.services.sandbox_runtime.firecracker_backend import (
                    FirecrackerSandboxBackend,
                )
                h = FirecrackerSandboxBackend().stop(dep)
            else:
                from lumen.engine.services.sandbox_runtime import select_sandbox_backend

                backend, _ = select_sandbox_backend(require_available=False)
                h = backend.stop(dep)
            return DeploymentStatus(
                status=DEPLOY_STOPPED,
                deployment_id=dep,
                message=h.message or "stopped",
            )
        except Exception as exc:
            return DeploymentStatus(
                status=DEPLOY_FAILED,
                deployment_id=dep,
                message=f"stop_error:{type(exc).__name__}:{exc}"[:300],
            )

    def restart(self, deployment_id: str) -> DeploymentStatus:
        # Restart requires original project_path/token — not stored on this adapter.
        return DeploymentStatus(
            status=DEPLOY_FAILED,
            deployment_id=deployment_id or "",
            message="sandbox_restart_requires_redeploy",
        )

    def logs(self, deployment_id: str, *, limit: int = 50) -> List[str]:
        dep = (deployment_id or "").strip()
        if not dep:
            return []
        try:
            if dep.startswith("fc-"):
                from lumen.engine.services.sandbox_runtime.firecracker_backend import (
                    FirecrackerSandboxBackend,
                )
                return FirecrackerSandboxBackend().logs(dep, limit=limit)
            from lumen.engine.services.sandbox_runtime import select_sandbox_backend

            backend, _ = select_sandbox_backend(require_available=False)
            return list(backend.logs(dep, limit=limit) or [])
        except Exception:
            return []
