"""Phase 5 — real agent host pipeline (not a thin wrapper).

Steps (always):
  1) Resolve project path (params / active_repo / last_project)
  2) Resolve bot token (params / sealed secrets)
  3) Plan quota when serverless
  4) Preflight: entrypoint + optional serverless adapt
  5) HostingService.start
  6) On serverless failure: repair once, then attach running instance to HostService
  7) Return structured result for tools + engine_turn (instance_id, lifecycle, urls)

User-facing text never mentions cloud vendors.
"""
from __future__ import annotations

import logging
import os
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

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
    project_path: str = ""
    data: dict[str, Any] = field(default_factory=dict)


def serverless_mode() -> bool:
    hb = (os.environ.get("TBE_HOST_BACKEND") or "").strip().lower()
    return hb in {"lumen_serverless", "serverless", "vercel"}


def resolve_project_path(
    *,
    params: dict[str, Any] | None = None,
    user_data: dict[str, Any] | None = None,
) -> str:
    params = dict(params or {})
    ud = dict(user_data or {})
    candidates = [
        params.get("project_path"),
        params.get("path"),
        (params.get("active_repo") or {}).get("path") if isinstance(params.get("active_repo"), dict) else None,
        (ud.get("active_repo") or {}).get("path") if isinstance(ud.get("active_repo"), dict) else None,
        ud.get("last_project_path"),
        ud.get("last_clone_path"),
    ]
    for c in candidates:
        p = str(c or "").strip()
        if p and Path(p).is_dir():
            return str(Path(p).resolve())
    return ""


def resolve_bot_token(
    project_path: str,
    *,
    params: dict[str, Any] | None = None,
    user_data: dict[str, Any] | None = None,
) -> str:
    params = dict(params or {})
    ud = dict(user_data or {})
    for key in ("token", "bot_token", "telegram_bot_token"):
        t = str(params.get(key) or ud.get(key) or "").strip()
        if t and ":" in t:
            return t
    try:
        from lumen.hosting.secrets_env import load_project_secrets
        sealed = load_project_secrets(project_path)
        t = (sealed.get("BOT_TOKEN") or sealed.get("TELEGRAM_BOT_TOKEN") or "").strip()
        if t and ":" in t:
            return t
    except Exception:
        pass
    return ""


def preflight_project(project_path: str) -> tuple[bool, str, dict[str, Any]]:
    root = Path(project_path)
    if not root.is_dir():
        return False, "مسار المشروع غير موجود", {}
    details: dict[str, Any] = {"path": str(root)}
    # Entry point
    entry = ""
    for name in ("main.py", "bot.py", "app.py", "run.py", "api/index.py"):
        if (root / name).is_file():
            entry = name
            break
    if not entry:
        py = list(root.glob("*.py"))
        if not py and not (root / "api").is_dir():
            return False, "المشروع لا يحتوي ملفات Python قابلة للتشغيل", details
        entry = py[0].name if py else "api/index.py"
    details["entry_point"] = entry

    if serverless_mode():
        try:
            from lumen.engine.services.hosting.prepare_runtime import prepare_project_for_serverless
            prep = prepare_project_for_serverless(root, entry_point=entry if entry != "api/index.py" else "")
            if not prep.ok:
                return False, prep.message or "فشل تجهيز المشروع للاستضافة", {"prepare": dict(prep.details or {})}
            details["prepare"] = dict(prep.details or {})
            details["entry_point"] = prep.entry_point or entry
        except Exception as exc:
            return False, f"فشل التجهيز: {type(exc).__name__}", details
    return True, "ok", details


def _hosting_service():
    from lumen.engine.services.hosting import get_hosting_service
    from lumen.engine.services.tool_runtime.executor import _output_dir
    return get_hosting_service(_output_dir())


def attach_serverless_instance(
    svc: Any,
    *,
    user_id: int,
    project_path: str,
    bot_token: str,
    tenant_id: str,
    deployment_id: str,
    public_url: str,
    webhook_url: str,
    meta: dict[str, Any] | None = None,
    instance_id: str = "",
) -> Any:
    """Persist a running serverless instance after external repair/deploy."""
    from lumen.engine.services.hosting.service import HostInstance
    from lumen.engine.services.hosting.contract import token_fingerprint

    meta = dict(meta or {})
    iid = (instance_id or f"host-{uuid.uuid4().hex[:10]}").strip()
    now = time.time()
    diag = {
        "lifecycle_state": str(meta.get("lifecycle_state") or "RUNNING"),
        "verify_ok": bool(meta.get("verify_ok", True)),
        "webhook_url": webhook_url or str(meta.get("webhook_url") or ""),
        "webhook_path": str(meta.get("webhook_path") or "/api"),
        "webhook_secret": str(meta.get("webhook_secret") or "")[:64],
        "provider": "lumen_serverless",
        "repaired": bool(meta.get("repaired") or meta.get("from_repair")),
    }
    inst = HostInstance(
        instance_id=iid,
        user_id=int(user_id),
        tenant_id=str(tenant_id or ""),
        project_path=str(project_path),
        entry_point=str(meta.get("entry_point") or ""),
        bot_username=str(meta.get("bot_username") or ""),
        status="running",
        deployment_id=str(deployment_id or meta.get("deployment_id") or ""),
        sandbox_backend="lumen_serverless",
        started_at=now,
        public_base_url=str(public_url or meta.get("url") or ""),
        webhook_public_url=diag["webhook_url"],
        token_fp=token_fingerprint(bot_token) if bot_token else "",
        last_diagnosis=diag,
        platform="telegram",
    )
    try:
        svc._instances[iid] = inst
        svc._save()
    except Exception:
        logger.exception("attach_serverless_instance save failed")
        raise
    # Webhook apply (idempotent if already verified)
    try:
        from lumen.hosting.webhook_manager import apply_to_instance
        apply_to_instance(instance_id=iid, bot_token=bot_token, inst=inst)
        svc._instances[iid] = inst
        svc._save()
    except Exception:
        logger.warning("apply_to_instance after attach failed", exc_info=True)
    return inst


def run_host_pipeline(
    *,
    user_id: int,
    project_path: str | Path = "",
    bot_token: str = "",
    tenant_id: str = "",
    bot_username: str = "",
    allow_repair: bool = True,
    params: dict[str, Any] | None = None,
    user_data: dict[str, Any] | None = None,
) -> PipelineResult:
    params = dict(params or {})
    user_data = dict(user_data or {})

    path = str(project_path or "").strip() or resolve_project_path(params=params, user_data=user_data)
    if not path:
        return PipelineResult(
            ok=False,
            message="ما فيش مشروع نشط. اسحب المستودع أو حدّد المسار أولاً.",
            data={"needs_project": True},
        )

    token = (bot_token or "").strip() or resolve_bot_token(path, params=params, user_data=user_data)
    if not token or ":" not in token:
        return PipelineResult(
            ok=False,
            message="مطلوب توكن بوت تيليجرام لإكمال الاستضافة.",
            project_path=path,
            data={"needs_bot_token": True, "project_path": path},
        )

    uid = int(user_id or 0)
    tenant = (tenant_id or params.get("tenant_id") or user_data.get("tenant_id") or (f"tg:{uid}" if uid else "")).strip()

    ok_pf, msg_pf, pf = preflight_project(path)
    if not ok_pf:
        return PipelineResult(ok=False, message=msg_pf, project_path=path, data={"preflight": pf})

    try:
        svc = _hosting_service()
    except Exception as exc:
        return PipelineResult(ok=False, message=f"خدمة الاستضافة غير متاحة: {type(exc).__name__}", project_path=path)

    if serverless_mode():
        try:
            from lumen.hosting.serverless_policy import assert_serverless_quota, count_serverless_running
            running = count_serverless_running(list(svc.list_for_user(uid)), user_id=uid)
            ok_q, reason = assert_serverless_quota(user_id=uid, running_serverless=running)
            if not ok_q:
                return PipelineResult(ok=False, message=reason, project_path=path, data={"quota": True})
        except Exception as exc:
            env = (os.environ.get("ENVIRONMENT") or "").lower()
            if env not in {"dev", "development", "local", "test"}:
                return PipelineResult(ok=False, message=f"quota_error:{type(exc).__name__}", project_path=path)

    try:
        result = svc.start(
            user_id=uid,
            project_path=path,
            bot_token=token,
            bot_username=bot_username or str(params.get("bot_username") or ""),
            tenant_id=tenant,
            entry_point=str(pf.get("entry_point") or ""),
        )
    except TypeError:
        result = svc.start(
            user_id=uid,
            project_path=path,
            bot_token=token,
            bot_username=bot_username or "",
            tenant_id=tenant,
        )
    except Exception as exc:
        logger.exception("pipeline start failed")
        return PipelineResult(ok=False, message=f"فشل بدء الاستضافة: {type(exc).__name__}", project_path=path)

    ok = bool(getattr(result, "ok", False))
    inst = getattr(result, "instance", None)
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
            project_path=path,
            data={
                "status": getattr(inst, "status", ""),
                "verify_ok": bool(diag.get("verify_ok")),
                "preflight": pf,
            },
        )

    # Serverless repair → attach real instance (not hollow ok)
    if allow_repair and serverless_mode():
        try:
            from lumen.hosting.serverless_repair import repair_serverless_project
            rep = repair_serverless_project(
                path,
                bot_token=token,
                user_id=uid,
                service_name=f"lumen-u{uid}-pipeline",
            )
        except Exception as exc:
            logger.warning("repair failed: %s", type(exc).__name__)
            rep = None
        if rep is not None and rep.ok:
            meta = dict(rep.meta or {})
            meta["from_repair"] = True
            meta["entry_point"] = pf.get("entry_point")
            meta["bot_username"] = bot_username
            try:
                inst2 = attach_serverless_instance(
                    svc,
                    user_id=uid,
                    project_path=path,
                    bot_token=token,
                    tenant_id=tenant,
                    deployment_id=rep.deployment_id,
                    public_url=rep.url,
                    webhook_url=str(meta.get("webhook_url") or ""),
                    meta=meta,
                    instance_id=str(getattr(inst, "instance_id", "") or "") if inst else "",
                )
            except Exception as exc:
                return PipelineResult(
                    ok=False,
                    message=f"تم النشر لكن فشل تسجيل المثيل: {type(exc).__name__}",
                    deployment_id=rep.deployment_id,
                    public_url=rep.url,
                    project_path=path,
                    data={"repaired": True, "attach_failed": True},
                )
            diag = dict(getattr(inst2, "last_diagnosis", None) or {})
            return PipelineResult(
                ok=True,
                message=rep.message or "تم إصلاح البوت وتفعيله على استضافة Lumen.",
                instance_id=str(inst2.instance_id),
                deployment_id=str(inst2.deployment_id or rep.deployment_id),
                public_url=str(inst2.public_base_url or rep.url),
                webhook_url=str(inst2.webhook_public_url or ""),
                lifecycle_state=str(diag.get("lifecycle_state") or "RUNNING"),
                backend="lumen_serverless",
                project_path=path,
                data={"repaired": True, "verify_ok": bool(diag.get("verify_ok")), "preflight": pf},
            )
        if rep is not None:
            return PipelineResult(
                ok=False,
                message=rep.message or msg or "فشل الاستضافة بعد محاولة الإصلاح",
                project_path=path,
                data={"repaired": False, "meta": dict(rep.meta or {})},
            )

    return PipelineResult(
        ok=False,
        message=msg or "فشل بدء الاستضافة",
        instance_id=str(getattr(inst, "instance_id", "") or "") if inst else "",
        backend=str(getattr(inst, "sandbox_backend", "") or "") if inst else "",
        project_path=path,
        data={"start_failed": True, "preflight": pf},
    )


def format_instances_status(instances: list[Any]) -> str:
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
        iid = str(getattr(inst, "instance_id", "") or "")[:18]
        lines.append(f"• [{kind}] `{iid}` — {st}" + (f" ({life})" if life else ""))
        if url:
            lines.append(f"  الرابط: {url}")
        if diag.get("verify_ok") is True:
            lines.append("  التحقق: ناجح")
        elif st == "running":
            lines.append("  التحقق: غير مؤكد")
        err = str(getattr(inst, "last_error", "") or "")
        if err and st != "running":
            lines.append(f"  خطأ: {err[:120]}")
    return "\n".join(lines)[:4000]


__all__ = [
    "PipelineResult",
    "run_host_pipeline",
    "format_instances_status",
    "resolve_project_path",
    "resolve_bot_token",
    "preflight_project",
    "attach_serverless_instance",
    "serverless_mode",
]
