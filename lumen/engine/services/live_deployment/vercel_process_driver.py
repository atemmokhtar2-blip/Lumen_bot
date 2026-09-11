"""Platform serverless deployment driver (internal).

Implements DeploymentProvider for Lumen-owned host account.
End-user messages never mention the underlying cloud vendor.
Provider id exposed as ``lumen_serverless`` only.
"""
from __future__ import annotations

import logging
import re
from typing import Dict, List, Optional

from .deployment_provider import DeploymentProvider
from .report_data import (
    DEPLOY_FAILED,
    DEPLOY_PENDING,
    DEPLOY_RUNNING,
    DEPLOY_STOPPED,
    DeploymentStatus,
)
from .vercel_client import (
    PlatformHostClient,
    collect_project_files,
    sanitize_project_name,
    token_configured,
)

logger = logging.getLogger("lumen.live_deployment.lumen_serverless")

_ID_RE = re.compile(r"^[A-Za-z0-9_.:-]{1,128}$")


def _user_msg(code: str) -> str:
    """Arabic operator-safe messages without vendor names."""
    mapping = {
        "token_missing": "الاستضافة غير مُعدّة على الخادم — راجع إعدادات المنصة.",
        "deploy_failed": "تعذّر نشر البوت على منصة Lumen.",
        "project_failed": "تعذّر تجهيز مساحة الاستضافة.",
        "env_failed": "تعذّر ضبط أسرار التشغيل.",
        "stopped": "تم إيقاف البوت.",
        "running": "البوت يعمل على استضافة Lumen.",
        "pending": "جاري النشر على استضافة Lumen…",
        "not_found": "لم يُعثر على عملية النشر.",
    }
    return mapping.get(code, "حدث خطأ أثناء الاستضافة.")


class VercelProcessDriver(DeploymentProvider):
    """Internal name kept for code navigation; public provider string is lumen_serverless."""

    name = "lumen_serverless"

    def __init__(self, client: PlatformHostClient | None = None) -> None:
        self._client = client or PlatformHostClient()

    def deploy(
        self,
        project_path: str,
        *,
        env_vars: Optional[Dict[str, str]] = None,
        service_name: str = "generated-bot",
    ) -> DeploymentStatus:
        if not self._client.configured and not token_configured():
            return DeploymentStatus(
                provider=self.name,
                status=DEPLOY_FAILED,
                message=_user_msg("token_missing"),
            )
        env = dict(env_vars or {})
        # Never accept empty path
        name = sanitize_project_name(service_name or "lumen-bot")
        try:
            files = collect_project_files(project_path)
        except Exception as exc:
            logger.warning("collect_files failed %s", type(exc).__name__)
            return DeploymentStatus(
                provider=self.name,
                status=DEPLOY_FAILED,
                message=_user_msg("deploy_failed"),
            )

        proj = self._client.ensure_project(name)
        if not proj.ok:
            logger.warning("ensure_project failed %s", proj.error)
            return DeploymentStatus(
                provider=self.name,
                status=DEPLOY_FAILED,
                message=_user_msg("project_failed"),
            )
        project_id = str(proj.mapping.get("id") or proj.mapping.get("projectId") or "")
        if not project_id and isinstance(proj.mapping.get("project"), dict):
            project_id = str((proj.mapping.get("project") or {}).get("id") or "")

        # Secrets as project env (prefer over embedding in files)
        if project_id:
            for key, val in env.items():
                if not key or val is None or val == "":
                    continue
                sensitive = key.upper() in {
                    "BOT_TOKEN",
                    "TELEGRAM_BOT_TOKEN",
                    "TOKEN",
                    "API_KEY",
                    "SECRET",
                } or "TOKEN" in key.upper() or "SECRET" in key.upper()
                er = self._client.upsert_env(project_id, key, str(val), sensitive=sensitive)
                if not er.ok:
                    # Non-fatal for non-token keys; fatal for bot token
                    if key.upper() in {"BOT_TOKEN", "TELEGRAM_BOT_TOKEN"}:
                        logger.warning("env upsert failed for secret key")
                        return DeploymentStatus(
                            provider=self.name,
                            project_id=project_id,
                            status=DEPLOY_FAILED,
                            message=_user_msg("env_failed"),
                        )

        # Do not send secrets again in deployment body if already on project
        deploy_env = {k: v for k, v in env.items() if k.upper() not in {"BOT_TOKEN", "TELEGRAM_BOT_TOKEN"}}
        dep = self._client.create_file_deployment(
            project_name=name,
            files=files,
            env=deploy_env or None,
        )
        if not dep.ok:
            logger.warning("deployment create failed %s", dep.error)
            return DeploymentStatus(
                provider=self.name,
                project_id=project_id,
                status=DEPLOY_FAILED,
                message=_user_msg("deploy_failed"),
            )
        d = dep.mapping
        dep_id = str(d.get("id") or d.get("uid") or "")
        url = str(d.get("url") or "")
        if url and not url.startswith("http"):
            url = f"https://{url}"
        ready = str(d.get("readyState") or d.get("status") or "").upper()
        st = DEPLOY_PENDING
        if ready in {"READY", "RUNNING"}:
            st = DEPLOY_RUNNING
        elif ready in {"ERROR", "CANCELED", "FAILED"}:
            st = DEPLOY_FAILED
        return DeploymentStatus(
            provider=self.name,
            deployment_id=dep_id,
            project_id=project_id,
            service_id=name,
            status=st,
            url=url,
            message=_user_msg("running" if st == DEPLOY_RUNNING else "pending"),
        )

    def status(self, deployment_id: str) -> DeploymentStatus:
        dep = (deployment_id or "").strip()
        if not dep or not _ID_RE.match(dep):
            return DeploymentStatus(provider=self.name, status=DEPLOY_STOPPED, message=_user_msg("not_found"))
        if not self._client.configured:
            return DeploymentStatus(provider=self.name, status=DEPLOY_FAILED, message=_user_msg("token_missing"))
        r = self._client.get_deployment(dep)
        if not r.ok:
            return DeploymentStatus(
                provider=self.name,
                deployment_id=dep,
                status=DEPLOY_FAILED if r.status != 404 else DEPLOY_STOPPED,
                message=_user_msg("not_found" if r.status == 404 else "deploy_failed"),
            )
        d = r.mapping
        url = str(d.get("url") or "")
        if url and not url.startswith("http"):
            url = f"https://{url}"
        ready = str(d.get("readyState") or "").upper()
        if ready == "READY":
            st = DEPLOY_RUNNING
            msg = _user_msg("running")
        elif ready in {"ERROR", "CANCELED"}:
            st = DEPLOY_FAILED
            msg = _user_msg("deploy_failed")
        elif ready in {"QUEUED", "BUILDING", "INITIALIZING"}:
            st = DEPLOY_PENDING
            msg = _user_msg("pending")
        else:
            st = DEPLOY_PENDING
            msg = _user_msg("pending")
        return DeploymentStatus(
            provider=self.name,
            deployment_id=dep,
            project_id=str(d.get("projectId") or ""),
            status=st,
            url=url,
            message=msg,
        )

    def stop(self, deployment_id: str) -> DeploymentStatus:
        dep = (deployment_id or "").strip()
        if not dep:
            return DeploymentStatus(provider=self.name, status=DEPLOY_STOPPED, message=_user_msg("stopped"))
        if self._client.configured and _ID_RE.match(dep):
            self._client.cancel_deployment(dep)
        return DeploymentStatus(
            provider=self.name,
            deployment_id=dep,
            status=DEPLOY_STOPPED,
            message=_user_msg("stopped"),
        )

    def restart(
        self,
        deployment_id: str,
        *,
        bot_token: str = "",
        project_path: str = "",
        env_vars: Optional[Dict[str, str]] = None,
    ) -> DeploymentStatus:
        self.stop(deployment_id)
        if not project_path:
            return DeploymentStatus(
                provider=self.name,
                deployment_id=deployment_id,
                status=DEPLOY_STOPPED,
                message=_user_msg("stopped"),
            )
        env = dict(env_vars or {})
        if bot_token:
            env.setdefault("BOT_TOKEN", bot_token)
            env.setdefault("TELEGRAM_BOT_TOKEN", bot_token)
        return self.deploy(project_path, env_vars=env, service_name=f"lumen-{deployment_id[:12]}")

    def logs(self, deployment_id: str, *, limit: int = 50) -> List[str]:
        # Phase 1: no log stream wiring yet — avoid vendor errors in UI
        return []


__all__ = ["VercelProcessDriver"]
