"""Lumen serverless host driver — real upload→deploy→wait protocol.

Public provider id: ``lumen_serverless`` (never vendor-branded in user text).
"""
from __future__ import annotations

import logging
import os
import re
from typing import Any,  Dict, List, Optional

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
    collect_local_files,
    sanitize_project_name,
    token_configured,
)

logger = logging.getLogger("lumen.live_deployment.lumen_serverless")

_ID_RE = re.compile(r"^[A-Za-z0-9_.:-]{1,128}$")


def _user_msg(code: str) -> str:
    return {
        "token_missing": "الاستضافة غير مُعدّة على خوادم Lumen.",
        "deploy_failed": "تعذّر نشر البوت على استضافة Lumen.",
        "project_failed": "تعذّر تجهيز مساحة الاستضافة.",
        "env_failed": "تعذّر ضبط أسرار التشغيل.",
        "upload_failed": "تعذّر رفع ملفات المشروع.",
        "timeout": "انتهت مهلة النشر — أعد المحاولة.",
        "stopped": "تم إيقاف البوت.",
        "running": "البوت يعمل على استضافة Lumen.",
        "pending": "جاري النشر على استضافة Lumen…",
        "not_found": "لم يُعثر على عملية النشر.",
    }.get(code, "حدث خطأ أثناء الاستضافة.")


def _wait_timeout() -> float:
    try:
        return float(os.getenv("LUMEN_SERVERLESS_WAIT_SEC") or "180")
    except ValueError:
        return 180.0


class VercelProcessDriver(DeploymentProvider):
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
        if not (self._client.configured or token_configured()):
            return DeploymentStatus(
                provider=self.name,
                status=DEPLOY_FAILED,
                message=_user_msg("token_missing"),
            )
        env = dict(env_vars or {})
        name = sanitize_project_name(service_name or "lumen-bot")
        try:
            files = collect_local_files(project_path)
        except Exception as exc:
            logger.warning("collect_local_files %s", type(exc).__name__)
            return DeploymentStatus(provider=self.name, status=DEPLOY_FAILED, message=_user_msg("deploy_failed"))

        proj = self._client.ensure_project(name)
        if not proj.ok:
            logger.warning("ensure_project %s", proj.error)
            return DeploymentStatus(provider=self.name, status=DEPLOY_FAILED, message=_user_msg("project_failed"))
        project_id = str(proj.mapping.get("id") or "")
        if not project_id and isinstance(proj.mapping.get("project"), dict):
            project_id = str((proj.mapping["project"] or {}).get("id") or "")

        # Encrypted project env for secrets (official type=encrypted).
        # BOT_TOKEN is mandatory; other keys soft-fail so deploy still proceeds.
        env_target = project_id or name
        token_ok = False
        for key, val in env.items():
            if not key or val is None or str(val) == "":
                continue
            upper = key.upper()
            is_secret = (
                upper in {"BOT_TOKEN", "TELEGRAM_BOT_TOKEN", "TOKEN"}
                or "TOKEN" in upper
                or "SECRET" in upper
                or "KEY" in upper
            )
            er = self._client.upsert_env(
                env_target,
                key,
                str(val),
                encrypted=is_secret,
                targets=["production", "preview"],
            )
            if er.ok and upper in {"BOT_TOKEN", "TELEGRAM_BOT_TOKEN"}:
                token_ok = True
            if not er.ok and upper in {"BOT_TOKEN", "TELEGRAM_BOT_TOKEN"}:
                logger.warning(
                    "bot token env failed status=%s err=%s — retry once",
                    er.status,
                    (er.error or "")[:120],
                )
                er2 = self._client.upsert_env(
                    env_target,
                    key,
                    str(val),
                    encrypted=True,
                    targets=["production", "preview"],
                )
                if er2.ok:
                    token_ok = True
                else:
                    logger.warning("bot token env failed after retry: %s", (er2.error or "")[:160])
        # Require at least one of BOT_TOKEN / TELEGRAM_BOT_TOKEN when provided
        need_token = any(
            (k or "").upper() in {"BOT_TOKEN", "TELEGRAM_BOT_TOKEN"} and v
            for k, v in env.items()
        )
        if need_token and not token_ok:
            return DeploymentStatus(
                provider=self.name,
                project_id=project_id,
                status=DEPLOY_FAILED,
                message=_user_msg("env_failed"),
            )

        dep = self._client.create_deployment_from_files(
            project_name=name,
            files=files,
            project_id=project_id,
        )
        if not dep.ok:
            # Real fallback: official inline base64+encoding
            logger.warning("sha deploy failed (%s); trying inline", dep.error)
            dep = self._client.create_inline_deployment(project_name=name, files=files)
        if not dep.ok:
            logger.warning("deployment failed %s", dep.error)
            code = "upload_failed" if "upload" in (dep.error or "") else "deploy_failed"
            return DeploymentStatus(
                provider=self.name,
                project_id=project_id,
                status=DEPLOY_FAILED,
                message=_user_msg(code),
            )

        d = dep.mapping
        dep_id = str(d.get("id") or d.get("uid") or "")
        url = str(d.get("url") or "")
        if url and not url.startswith("http"):
            url = f"https://{url}"

        # Wait for READY when possible (real readiness, not "accepted")
        if dep_id and self._client.configured:
            waited = self._client.wait_ready(dep_id, timeout_sec=_wait_timeout())
            if waited.ok:
                d = waited.mapping
                raw = str(d.get("url") or url)
                if raw and not raw.startswith("http"):
                    raw = f"https://{raw}"
                public = self._client.resolve_public_url(
                    deployment_id=dep_id,
                    project_name=name,
                    fallback_url=raw,
                )
                url = public or raw
                return DeploymentStatus(
                    provider=self.name,
                    deployment_id=dep_id,
                    project_id=project_id or str(d.get("projectId") or ""),
                    service_id=name,
                    status=DEPLOY_RUNNING,
                    url=url,
                    message=_user_msg("running"),
                )
            if (waited.error or "").startswith("deploy_"):
                return DeploymentStatus(
                    provider=self.name,
                    deployment_id=dep_id,
                    project_id=project_id,
                    status=DEPLOY_FAILED,
                    url=url,
                    message=_user_msg("timeout" if "timeout" in (waited.error or "") else "deploy_failed"),
                )

        ready = str(d.get("readyState") or "").upper()
        st = DEPLOY_RUNNING if ready == "READY" else DEPLOY_PENDING
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
                status=DEPLOY_STOPPED if r.status == 404 else DEPLOY_FAILED,
                message=_user_msg("not_found" if r.status == 404 else "deploy_failed"),
            )
        d = r.mapping
        url = str(d.get("url") or "")
        if url and not url.startswith("http"):
            url = f"https://{url}"
        ready = str(d.get("readyState") or "").upper()
        if ready == "READY":
            return DeploymentStatus(
                provider=self.name, deployment_id=dep, project_id=str(d.get("projectId") or ""),
                status=DEPLOY_RUNNING, url=url, message=_user_msg("running"),
            )
        if ready in {"ERROR", "CANCELED"}:
            return DeploymentStatus(
                provider=self.name, deployment_id=dep, status=DEPLOY_FAILED, url=url, message=_user_msg("deploy_failed"),
            )
        return DeploymentStatus(
            provider=self.name, deployment_id=dep, status=DEPLOY_PENDING, url=url, message=_user_msg("pending"),
        )

    def stop(self, deployment_id: str) -> DeploymentStatus:
        dep = (deployment_id or "").strip()
        if dep and self._client.configured and _ID_RE.match(dep):
            # Prefer hard delete (removes public URL) then cancel as fallback
            deleted = self._client.delete_deployment(dep)
            if not deleted.ok:
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
                provider=self.name, deployment_id=deployment_id, status=DEPLOY_STOPPED, message=_user_msg("stopped"),
            )
        env = dict(env_vars or {})
        if bot_token:
            env.setdefault("BOT_TOKEN", bot_token)
            env.setdefault("TELEGRAM_BOT_TOKEN", bot_token)
        return self.deploy(project_path, env_vars=env, service_name=sanitize_project_name(f"lumen-{deployment_id[:12]}"))

    def logs(self, deployment_id: str, *, limit: int = 50) -> List[str]:
        dep = (deployment_id or "").strip()
        if not dep or not _ID_RE.match(dep) or not self._client.configured:
            return []
        try:
            r = self._client.list_deployment_events(dep, limit=max(1, min(100, int(limit))))
        except Exception:
            return []
        if not r.ok:
            return []
        rows: List[Any] = []
        data = r.data
        if isinstance(data, list):
            rows = data
        elif isinstance(data, dict):
            rows = list(data.get("events") or data.get("builds") or data.get("payloads") or [])
        out: List[str] = []
        for row in rows[-int(limit):]:
            if isinstance(row, str):
                out.append(row[:500])
                continue
            if not isinstance(row, dict):
                continue
            text = (
                str(row.get("text") or row.get("payload") or row.get("message") or row.get("type") or "")
            ).strip()
            ts = str(row.get("created") or row.get("date") or row.get("timestamp") or "")
            if text:
                out.append(f"{ts} {text}"[:500] if ts else text[:500])
        return out[-int(limit):]


__all__ = ["VercelProcessDriver"]
