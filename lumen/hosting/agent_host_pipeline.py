"""Phase 5 — agent host pipeline: active project → host → verify → status.

Single real path used by tool host_start when the platform backend is
lumen_serverless. Firecracker path continues via HostingService.start directly.

No fixed NL commands; tools/agent call this with structured params.
"""
from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger("lumen.hosting.agent_host_pipeline")


@dataclass
class PipelineResult:
    ok: bool
    message: str = ""
    instance_id: str = ""
    deployment_id: str = ""
    public_url: str = ""
    webhook_url: str = ""
    lifecycle_state: str = ""
    backend: str = ""
    data: dict[str, Any] = field(default_factory=dict)


def _serverless_mode() -> bool:
    hb = (os.environ.get("TBE_HOST_BACKEND") or "").strip().lower()
    return hb in {"lumen_serverless", "serverless", "vercel"}


def run_host_pipeline(
    *,
    user_id: int,
    project_path: str | Path,
    bot_token: str,
    tenant_id: str = "",
    bot_username: str = "",
    allow_repair: bool = True,
) -> PipelineResult:
    """Start hosting for an agent-selected project path.

    Serverless: prepare is inside orchestration; on failure try one repair.
    Permanent: HostingService.start (Firecracker) as today.
    """
    root = Path(project_path).resolve()
    if not root.is_dir():
        return PipelineResult(ok=False, message="مسار المشروع غير موجود")

    token = (bot_token or "").strip()
    if not token or ":" not in token:
        return PipelineResult(
            ok=False,
            message="مطلوب توكن بوت تيليجرام لإكمال الاستضافة.",
            data={"needs_bot_token": True},
        )

    uid = int(user_id or 0)
    tenant = (tenant_id or (f"tg:{uid}" if uid else "")).strip()

    try:
        from lumen.engine.services.hosting import get_hosting_service
        from lumen.engine.services.tool_runtime.executor import _output_dir

        svc = get_hosting_service(_output_dir())
    except Exception as exc:
        logger.exception("host service unavailable")
        return PipelineResult(ok=False, message=f"خدمة الاستضافة غير متاحة: {type(exc).__name__}")

    # Quota (serverless) before heavy work
    if _serverless_mode():
        try:
            from lumen.hosting.serverless_policy import (
                assert_serverless_quota,
                count_serverless_running,
            )

            running = count_serverless_running(list(svc.list_for_user(uid)), user_id=uid)
            ok_q, reason = assert_serverless_quota(user_id=uid, running_serverless=running)
            if not ok_q:
                return PipelineResult(ok=False, message=reason, data={"quota": True})
        except Exception as exc:
            env = (os.environ.get("ENVIRONMENT") or "").lower()
            if env not in {"dev", "development", "local", "test"}:
                return PipelineResult(ok=False, message=f"quota_error:{type(exc).__name__}")

    try:
        result = svc.start(
            user_id=uid,
            project_path=str(root),
            bot_token=token,
            bot_username=bot_username or "",
            tenant_id=tenant,
        )
    except Exception as exc:
        logger.exception("pipeline start failed")
        return PipelineResult(ok=False, message=f"فشل بدء الاستضافة: {type(exc).__name__}")

    ok = bool(getattr(result, "ok", False))
    inst = getattr(result, "instance", None)
    msg = ""
    try:
        msg = result.to_user_text() if hasattr(result, "to_user_text") else str(getattr(result, "message", "") or "")
    except Exception:
        msg = str(getattr(result, "message", "") or "")

    if ok and inst is not None:
        diag = dict(getattr(inst, "last_diagnosis", None) or {})
        return PipelineResult(
            ok=True,
            message=msg or "البوت يعمل على استضافة Lumen.",
            instance_id=str(getattr(inst, "instance_id", "") or ""),
            deployment_id=str(getattr(inst, "deployment_id", "") or ""),
            public_url=str(getattr(inst, "public_base_url", "") or ""),
            webhook_url=str(getattr(inst, "webhook_public_url", "") or diag.get("webhook_url") or ""),
            lifecycle_state=str(diag.get("lifecycle_state") or ""),
            backend=str(getattr(inst, "sandbox_backend", "") or ""),
            data={
                "status": getattr(inst, "status", ""),
                "verify_ok": bool(diag.get("verify_ok")),
            },
        )

    # One repair attempt for serverless failures
    if allow_repair and _serverless_mode():
        try:
            from lumen.hosting.serverless_repair import repair_serverless_project

            rep = repair_serverless_project(
                root,
                bot_token=token,
                user_id=uid,
                service_name=f"lumen-u{uid}-pipeline",
            )
            if rep.ok:
                # Register instance via a second start if possible, else return repair meta
                return PipelineResult(
                    ok=True,
                    message=rep.message or "تم إصلاح البوت وتفعيله على استضافة Lumen.",
                    deployment_id=rep.deployment_id,
                    public_url=rep.url,
                    webhook_url=str((rep.meta or {}).get("webhook_url") or ""),
                    lifecycle_state=str((rep.meta or {}).get("lifecycle_state") or "RUNNING"),
                    backend="lumen_serverless",
                    data={"repaired": True, "meta": dict(rep.meta or {})},
                )
            return PipelineResult(
                ok=False,
                message=rep.message or msg or "فشل الاستضافة بعد محاولة الإصلاح",
                data={"repaired": False, "meta": dict(rep.meta or {})},
            )
        except Exception as exc:
            logger.warning("pipeline repair failed: %s", type(exc).__name__)

    return PipelineResult(
        ok=False,
        message=msg or "فشل بدء الاستضافة",
        instance_id=str(getattr(inst, "instance_id", "") or "") if inst else "",
        backend=str(getattr(inst, "sandbox_backend", "") or "") if inst else "",
        data={"start_failed": True},
    )


def format_instances_status(instances: list[Any]) -> str:
    """Arabic status block for agent host_status — no vendor names."""
    if not instances:
        return "ما فيش مثيلات استضافة حالياً."
    lines = ["حالة الاستضافة:"]
    for inst in instances:
        st = str(getattr(inst, "status", "") or "—")
        backend = str(getattr(inst, "sandbox_backend", "") or "")
        kind = "سريعة" if backend == "lumen_serverless" else ("دائمة" if backend == "firecracker" else "استضافة")
        diag = dict(getattr(inst, "last_diagnosis", None) or {})
        life = str(diag.get("lifecycle_state") or "")
        url = str(getattr(inst, "public_base_url", "") or "")
        iid = str(getattr(inst, "instance_id", "") or "")[:16]
        lines.append(f"• [{kind}] `{iid}` — {st}" + (f" ({life})" if life else ""))
        if url:
            lines.append(f"  الرابط: {url}")
        if diag.get("verify_ok") is True:
            lines.append("  التحقق: ناجح")
        elif diag.get("verify_ok") is False:
            lines.append("  التحقق: فشل")
    return "\n".join(lines)[:4000]


__all__ = ["PipelineResult", "run_host_pipeline", "format_instances_status"]
