"""Dashboard — HostService list/status/stop/diagnose with stable index targets."""
from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger("lumen_bot.ui")


def sync_dashboard_slots(user_id: int, state_slots: dict[str, str]) -> dict[str, str]:
    """Replace dash_* slots from live HostService.list_for_user."""
    slots = {k: v for k, v in (state_slots or {}).items() if not str(k).startswith("dash_")}
    try:
        from lumen.bot.config import OUTPUT_DIR
        from lumen.engine.services.hosting import get_hosting_service

        svc = get_hosting_service(OUTPUT_DIR)
        # Prefer store reload if service exposes it
        try:
            reload = getattr(svc, "reload", None) or getattr(svc, "_load", None)
            if callable(reload):
                reload()
        except Exception:
            pass
        items = list(svc.list_for_user(int(user_id)))
        items = sorted(
            items,
            key=lambda x: float(getattr(x, "started_at", 0) or 0),
            reverse=True,
        )
        for i, inst in enumerate(items[:5]):
            iid = str(getattr(inst, "instance_id", "") or "")
            slots[f"dash_h{i}"] = iid
            slots[f"dash_s{i}"] = str(getattr(inst, "status", "") or "")[:24]
            un = str(getattr(inst, "bot_username", "") or "")
            if un:
                slots[f"dash_u{i}"] = un[:32]
            path = str(getattr(inst, "project_path", "") or "")
            if path:
                slots[f"dash_p{i}"] = path[-80:]
            be = str(getattr(inst, "sandbox_backend", "") or "")
            if be:
                slots[f"dash_b{i}"] = be[:20]
        slots["dash_count"] = str(len(items))
    except Exception:
        logger.exception("sync_dashboard_slots failed")
        slots["dash_count"] = "0"
    return slots


def resolve_instance_id(target: str, slots: dict[str, str]) -> str | None:
    """Resolve dashboard target to an instance_id owned by this session.

    Only indices and IDs already present in dash_* slots are accepted.
    Never returns an arbitrary client-supplied ID (IDOR defense-in-depth;
    HostService.get still enforces user_id ownership).
    """
    target = (target or "").strip()
    if not target or target == "all":
        return None
    if target.isdigit():
        full = (slots.get(f"dash_h{int(target)}") or "").strip()
        return full or None
    for i in range(5):
        full = (slots.get(f"dash_h{i}") or "").strip()
        if not full:
            continue
        if full == target or (len(target) >= 8 and full.endswith(target)):
            return full
    return None


def format_host_result(result) -> str:
    """Plain text for Telegram (no broken Markdown)."""
    try:
        ok = bool(getattr(result, "ok", False))
        msg = str(getattr(result, "message", "") or "")
        lines = [("OK" if ok else "FAIL") + " | " + msg]
        inst = getattr(result, "instance", None)
        if inst is not None:
            lines.append(f"id: {getattr(inst, 'instance_id', '')}")
            lines.append(f"status: {getattr(inst, 'status', '')}")
            if getattr(inst, "bot_username", None):
                lines.append(f"bot: @{inst.bot_username}")
            if getattr(inst, "sandbox_backend", None):
                lines.append(f"backend: {inst.sandbox_backend}")
            if getattr(inst, "project_path", None):
                try:
                    from lumen.bot.ui.rtl_text import code_path
                    lines.append(f"path: {code_path(str(inst.project_path))}")
                except Exception:
                    lines.append(f"path: `{inst.project_path}`")
            if getattr(inst, "last_error", None):
                lines.append(f"error: {str(inst.last_error)[:300]}")
            if getattr(inst, "pid", None):
                lines.append(f"pid: {inst.pid}")
        contract = getattr(result, "error_contract", None)
        if contract is not None:
            try:
                summary = getattr(contract, "summary_ar", None) or getattr(contract, "message", None)
                if summary:
                    lines.append(f"diag: {str(summary)[:400]}")
            except Exception:
                pass
        return "\n".join(lines)[:3500]
    except Exception:
        return str(result)[:1500]


async def execute_dash_effect(
    *,
    effect: str,
    target: str,
    user_id: int,
    user_data: dict[str, Any],
    message,
) -> str:
    import asyncio

    from lumen.bot.config import OUTPUT_DIR
    from lumen.engine.services.hosting import get_hosting_service

    try:
        svc = get_hosting_service(OUTPUT_DIR)
    except Exception as exc:
        logger.exception("HostService unavailable for dash effect=%s", effect)
        return (
            "❌ خدمة الاستضافة غير متاحة حالياً.\n"
            f"• السبب: {type(exc).__name__}\n"
            "• تأكد من DATABASE_URL (Postgres) أو ENVIRONMENT=dev للاختبار المحلي."
        )
    try:
        from lumen.bot.ui.state_store import load_ui_state
        slots = dict(load_ui_state(user_data).slots or {})
    except Exception:
        slots = {}

    # Always refresh map before acting
    slots = sync_dashboard_slots(user_id, slots)
    try:
        from lumen.bot.ui.state_store import load_ui_state, save_ui_state
        st = load_ui_state(user_data)
        st.slots = slots
        save_ui_state(user_data, st)
    except Exception:
        pass

    if effect == "dash_status" and (not target or target == "all"):
        def _all():
            return svc.status(user_id=user_id, instance_id=None)
        result = await asyncio.to_thread(_all)
        return format_host_result(result)

    iid = resolve_instance_id(target, slots)
    if effect in {"dash_status", "dash_stop", "dash_diagnose", "dash_logs", "dash_backup", "dash_versions"} and not iid:
        return (
            "لا مثيل مطابق.\n"
            f"target={target!r} count={slots.get('dash_count', '?')}\n"
            "اضغط «تحديث القائمة»."
        )

    if effect == "dash_status":
        def _st():
            return svc.status(user_id=user_id, instance_id=iid)
        return format_host_result(await asyncio.to_thread(_st))

    if effect == "dash_stop":
        def _sp():
            return svc.stop(instance_id=str(iid), user_id=user_id)
        return format_host_result(await asyncio.to_thread(_sp))

    if effect == "dash_diagnose":
        def _dg():
            return svc.diagnose(user_id=user_id, instance_id=str(iid))
        return format_host_result(await asyncio.to_thread(_dg))

    if effect == "dash_logs":
        def _lg():
            return svc.logs(user_id=user_id, instance_id=str(iid), limit=60)
        result = await asyncio.to_thread(_lg)
        body = str(getattr(result, "message", "") or "")
        if getattr(result, "ok", False) and body:
            header = "📝 السجلات الحية (مجمّعة)"
            inst = getattr(result, "instance", None)
            if inst is not None and getattr(inst, "instance_id", None):
                header += f" · `{str(inst.instance_id)[:12]}`"
            return f"{header}\n\n```\n{body[:3200]}\n```"
        return format_host_result(result)

    if effect == "dash_backup":
        def _bk():
            inst = svc.get(str(iid), user_id=user_id)
            if inst is None:
                return {"ok": False, "error": "المثيل غير موجود"}
            from lumen.hosting.backup_manager import backup_project
            return backup_project(inst.project_path, instance_id=inst.instance_id)
        res = await asyncio.to_thread(_bk)
        if not res.get("ok"):
            return f"❌ فشل النسخ الاحتياطي: {res.get('error', 'unknown')}"
        return (
            f"✅ تم النسخ الاحتياطي\n"
            f"• الملفات: {res.get('file_count')}\n"
            f"• الحجم: {res.get('bytes')} بايت\n"
            f"• المسار: `{str(res.get('path') or '')[-80:]}`\n"
            f"• S3: {res.get('s3') or 'محلي فقط'}"
        )

    if effect == "dash_versions":
        def _vr():
            inst = svc.get(str(iid), user_id=user_id)
            if inst is None:
                return None
            from lumen.engine.services.hosting.versions import list_versions
            return list_versions(inst.project_path)
        vers = await asyncio.to_thread(_vr)
        if vers is None:
            return "❌ المثيل غير موجود"
        if not vers:
            return "لا إصدارات محفوظة بعد لهذا المشروع."
        lines = ["📦 إصدارات النشر:"]
        for v in list(vers)[:10]:
            lines.append(
                f"• `{str(v.get('version_ref') or '')[:12]}` — "
                f"{v.get('artifact_uri') or v.get('job_key') or ''}"
            )
        return "\n".join(lines)[:3500]

    return "إجراء لوحة غير معروف."
