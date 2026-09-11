"""Phase 4 — repair + redeploy for Lumen serverless hosts.

Real path: force re-adapt → start_host (deploy+verify) → return handle.
No fixed user commands; callable from HostService.restart / control plane.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger("lumen.hosting.serverless_repair")


@dataclass
class RepairResult:
    ok: bool
    message: str = ""
    deployment_id: str = ""
    url: str = ""
    meta: dict[str, Any] = field(default_factory=dict)


def repair_serverless_project(
    project_path: str | Path,
    *,
    bot_token: str,
    user_id: int = 0,
    service_name: str = "",
    env_vars: dict[str, str] | None = None,
) -> RepairResult:
    root = Path(project_path).resolve()
    if not root.is_dir():
        return RepairResult(ok=False, message="مسار المشروع غير موجود")

    token = (bot_token or "").strip()
    if not token or ":" not in token:
        return RepairResult(ok=False, message="توكن البوت غير صالح للإصلاح")

    # Force re-adapt (polling neutralize + adapter)
    try:
        from lumen.hosting.serverless_webhook_adapter import adapt_project_for_serverless

        adapted = adapt_project_for_serverless(root, force=True)
        if not adapted.ok:
            return RepairResult(ok=False, message=adapted.message or "فشل إعادة تجهيز Webhook")
    except Exception as exc:
        logger.warning("repair adapt failed: %s", type(exc).__name__)
        return RepairResult(ok=False, message="فشل إعادة تجهيز المشروع")

    env = dict(env_vars or {})
    env.setdefault("BOT_TOKEN", token)
    env.setdefault("TELEGRAM_BOT_TOKEN", token)

    try:
        from lumen.hosting.orchestration import start_host

        backend, handle = start_host(
            project_path=str(root),
            bot_token=token,
            user_id=int(user_id or 0),
            service_name=service_name or f"lumen-u{int(user_id or 0)}-repair",
            env_vars=env,
            backend="lumen_serverless",
        )
    except Exception as exc:
        logger.warning("repair start_host failed: %s", type(exc).__name__)
        return RepairResult(ok=False, message=f"فشل إعادة النشر: {type(exc).__name__}")

    meta = dict(getattr(handle, "meta", None) or {})
    if not getattr(handle, "ok", False) or str(getattr(handle, "status", "") or "") != "running":
        return RepairResult(
            ok=False,
            message=str(getattr(handle, "message", None) or "فشل التحقق بعد الإصلاح")[:500],
            deployment_id=str(getattr(handle, "deployment_id", "") or ""),
            url=str(meta.get("url") or ""),
            meta=meta,
        )

    return RepairResult(
        ok=True,
        message=str(getattr(handle, "message", None) or "تم إصلاح البوت وتفعيله على استضافة Lumen.")[:500],
        deployment_id=str(getattr(handle, "deployment_id", "") or ""),
        url=str(meta.get("url") or ""),
        meta=meta,
    )


__all__ = ["RepairResult", "repair_serverless_project"]
