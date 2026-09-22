"""Batch 3 — real plane binding for trial / permanent host / zip / preview."""
from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any

from .project_resolve import bind_active_repo, resolve_entry_point, resolve_project_path

logger = logging.getLogger("lumen_bot.ui")

_SECRET_NAME_PARTS = (
    "token", "secret", "password", "credential", ".env", "api_key", "private",
)


def _is_sensitive_name(name: str) -> bool:
    low = name.lower()
    return any(p in low for p in _SECRET_NAME_PARTS)



def _payload_project_kind(ud: dict) -> str:
    """Kind for plane payloads — never invent telegram_bot for unknown."""
    try:
        eu = ud.get("engine_ui") if isinstance(ud.get("engine_ui"), dict) else {}
        slots = eu.get("slots") if isinstance(eu.get("slots"), dict) else {}
        pk = str(slots.get("project_kind") or ud.get("project_kind") or "").strip()
        if pk:
            return pk
        # trial path only makes sense as telegram when surface says so
        surf = _surface_for_ud(ud)
        if surf == "telegram_runtime":
            return "telegram_bot"
        return "general_app"
    except Exception:
        return "general_app"

def _live_seconds(user) -> int:
    try:
        from lumen.bot.helpers import plan_live_seconds  # type: ignore
        return int(plan_live_seconds(user))
    except Exception:
        pass
    try:
        # message_router helper is often imported as _plan_live_seconds pattern
        from lumen.platform.plans import get_plan
        from lumen.bot.middlewares.mongo_sync import mongo_plan_for_user
        uid = int(getattr(user, "id", 0) or 0)
        plan_id = mongo_plan_for_user(uid) or "free"
        pd = get_plan(plan_id)
        mins = int(getattr(pd, "live_preview_minutes", 0) or 0)
        if mins > 0:
            return mins * 60
    except Exception:
        logger.debug("plan live seconds unavailable", exc_info=True)
    return int(os.environ.get("LIVE_RUN_SECONDS", "1800") or 1800)


def _persist(uid: int, ud: dict) -> str:
    """Persist session. Returns empty string on success, Arabic warning on failure."""
    try:
        from lumen.bot.session_store import get_session_store
        if uid:
            get_session_store().save(uid, dict(ud))
        return ""
    except Exception as exc:
        logger.exception("session persist failed")
        return (
            "\n⚠️ تعذر حفظ الجلسة على الخادم "
            f"({type(exc).__name__}). أبقِ هذه المحادثة مفتوحة وأعد اختيار المسار إن انقطع الاتصال."
        )


def _host_backend_hint() -> str:
    try:
        from lumen.engine.services.sandbox_runtime.select import (
            is_production_sandbox_path,
            probe_all,
        )
        if is_production_sandbox_path():
            for p in probe_all():
                if p.name == "firecracker":
                    return f"firecracker:{'ready' if p.available else p.reason}"
            return "firecracker:required"
        probes = probe_all()
        for p in probes:
            if p.available:
                return f"{p.name}:available"
        return "no_backend"
    except Exception as exc:
        return f"probe_error:{type(exc).__name__}"


def _surface_for_ud(ud: dict) -> str:
    """delivery_surface from UI slots or generation metadata (honest gate)."""
    try:
        from lumen.engine.core.project_kind import (
            DeliverySurface,
            ProjectKind,
            delivery_surface,
            parse_kind,
        )
        slots = {}
        eu = ud.get("engine_ui") if isinstance(ud.get("engine_ui"), dict) else {}
        if isinstance(eu.get("slots"), dict):
            slots = eu["slots"]
        pk = parse_kind(slots.get("project_kind") or ud.get("project_kind"))
        if pk is None:
            # Prefer explicit surface slot; never assume telegram for unknown kind
            raw = (slots.get("delivery_surface") or ud.get("delivery_surface") or "").strip()
            if raw in {"telegram_runtime", "http_runtime", "artifact_only"}:
                return raw
            return DeliverySurface.ARTIFACT_ONLY.value
        return delivery_surface(pk).value
    except Exception:
        return "telegram_runtime"


async def execute_post_side_effect(

    *,
    effect: str,
    project_ref: str,
    message,
    context,
    user,
) -> str:
    effect = (effect or "").strip()
    ud = context.user_data if context.user_data is not None else {}
    uid = int(getattr(user, "id", 0) or 0)
    if effect in {"tpl_reserve_trial", "tpl_reserve_permanent", "tpl_stop_instance"}:
        from lumen.bot.ui.callbacks.templates_actions import execute_template_reserve
        return await execute_template_reserve(
            effect=effect,
            user_id=int(uid or 0),
            user_data=ud if isinstance(ud, dict) else {},
            message=message,
        )

    root = resolve_project_path(project_ref, ud)
    if root is None and effect in {"post_trial", "post_host", "post_zip", "post_preview"}:
        return "لا يوجد مشروع على القرص — ولّد بوت أو اربط مشروعاً نشطاً أولاً."

    if effect == "post_trial":
        if _surface_for_ud(ud) != "telegram_runtime":
            return (
                "هذا المشروع ليس بوت تيليجرام — التجربة في الشات غير متاحة.\n"
                "استخدم ZIP أو معاينة الملفات."
            )
        assert root is not None
        entry = resolve_entry_point(root)
        if not (root / entry).is_file() and not any((root / n).is_file() for n in ("main.py", "bot.py")):
            return f"المشروع موجود لكن لا نقطة دخول واضحة تحت `{root}`."
        seconds = _live_seconds(user)
        from lumen.engine.services.runtime_planes import RuntimePlane, plane_label_ar

        payload = {
            "project_path": str(root),
            "owner_user_id": uid or None,
            "entry_point": entry,
            "run_seconds": seconds,
            "sandbox": True,
            "plane": RuntimePlane.TRIAL_CHAT.value,
            "project_kind": _payload_project_kind(ud),
        }
        ud["pending_run"] = dict(payload)
        ud["pending_live_run"] = dict(payload)
        ud["pending_deploy"] = dict(payload)
        ud.pop("pending_host", None)
        bind_active_repo(ud, root, entry=entry)
        persist_note = _persist(uid, ud)
        label = plane_label_ar(RuntimePlane.TRIAL_CHAT)
        if message is not None:
            try:
                from lumen.bot.ui.secret_prompt import prompt_for_secret

                body = (
                    f"✅ {label} — مربوط بـ `{root}`\n"
                    f"• نقطة الدخول: `{entry}`\n"
                    f"• المدة التقريبية: {seconds // 60} دقيقة\n"
                    f"• المستوى: trial_chat (LiveRunner — ليس HostService)\n"
                    f"{persist_note}\n"
                    "يلزم توكن البوت من @BotFather للتجربة المؤقتة."
                )
                await prompt_for_secret(
                    message=message, kind="bot", body=body, user_id=int(uid or 0)
                )
                return ""
            except Exception:
                logger.exception("trial secret prompt failed")
        return (
            f"✅ {label} — مربوط بـ `{root}`\n"
            f"• نقطة الدخول: `{entry}`\n"
            f"• المدة التقريبية: {seconds // 60} دقيقة\n"
            f"• المستوى: trial_chat (LiveRunner — ليس HostService)\n"
            f"{persist_note}\n\n"
            "أرسل توكن البوت من @BotFather الآن لبدء التشغيل التجريبي."
        )

    if effect == "post_host":
        _surf = _surface_for_ud(ud)
        if _surf == "artifact_only":
            return (
                "لا توجد قاعدة رابط عام (LUMEN_PUBLIC_BASE).\n"
                "حمّل ZIP أو اضبط الدومين على السيرفر ثم أعد الاستضافة."
            )
        if _surf == "http_runtime":
            try:
                from lumen.engine.core.project_kind import http_runtime_hints, parse_kind
                eu = ud.get("engine_ui") if isinstance(ud.get("engine_ui"), dict) else {}
                slots = eu.get("slots") if isinstance(eu.get("slots"), dict) else {}
                hints = http_runtime_hints(
                    project_ref=str(project_ref or (root or "")),
                    kind=parse_kind(slots.get("project_kind")),
                )
                ud["pending_host"] = {
                    "project_path": str(root) if root else str(project_ref or ""),
                    "owner_user_id": uid or None,
                    "plane": "http_public",
                    "project_kind": str(slots.get("project_kind") or "web_api"),
                    "public_url": hints.get("public_url") or "",
                    "health_path": hints.get("health_path") or "/health",
                    "start_hint": hints.get("start_hint") or "",
                }
                warn = _persist(uid, ud)
                url = hints.get("public_url") or "(غير مضبوط)"
                return (
                    f"تم تجهيز استضافة HTTP.\n"
                    f"الرابط: {url}\n"
                    f"فحص الصحة: {hints.get('health_path') or '/health'}\n"
                    "التشغيل الفعلي على الـ VPS يتبع إعداد الحاوية/البروكسي."
                    + warn
                )
            except Exception as exc:
                logger.exception("http post_host failed")
                return f"تعذر تجهيز استضافة HTTP: {type(exc).__name__}"
        if _surf != "telegram_runtime":
            return (
                "مسار الاستضافة غير مدعوم لهذا النوع.\n"
                "استخدم ZIP أو معاينة الملفات."
            )
        assert root is not None
        # Permanent host is a Pro entitlement — free users get trial only
        try:
            from lumen.platform.entitlement import resolve_pro_entitlement

            if uid and resolve_pro_entitlement(int(uid)) is None:
                return (
                    "🔒 الاستضافة الدائمة متاحة لمشتركي Lumen Pro فقط.\n"
                    "يمكنك استخدام «تجربة في الشات» مؤقتاً، "
                    "أو اشترك في Pro ثم أعد «استضافة دائمة»."
                )
        except Exception:
            logger.exception("pro entitlement check for post_host failed")
        entry = resolve_entry_point(root)
        backend = _host_backend_hint()
        from lumen.engine.services.runtime_planes import RuntimePlane, plane_label_ar

        ud["pending_host"] = {
            "project_path": str(root),
            "user_id": uid,
            "entry_point": entry,
            "plane": RuntimePlane.PERMANENT_HOST.value,
            "project_kind": _payload_project_kind(ud),
            "backend_hint": backend,
        }
        # Token must hit HostService, not trial LiveRunner
        ud.pop("pending_run", None)
        ud.pop("pending_live_run", None)
        ud.pop("pending_deploy", None)
        bind_active_repo(ud, root, entry=entry)
        persist_note = _persist(uid, ud)
        label = plane_label_ar(RuntimePlane.PERMANENT_HOST)
        warn = ""
        if "firecracker" in backend and "ready" not in backend and "available" not in backend:
            warn = (
                "\n⚠️ تنبيه: مسار الإنتاج يتطلب Firecracker "
                f"({backend}). على بيئة التطوير قد يُستخدم بديل مصرّح فقط."
            )
        if message is not None:
            try:
                from lumen.bot.ui.secret_prompt import prompt_for_secret

                body = (
                    f"✅ {label} — مربوط بـ `{root}`\n"
                    f"• نقطة الدخول: `{entry}`\n"
                    f"• العزل المتوقع: {backend}\n"
                    f"• المستوى: permanent_host (HostService.start)\n"
                    f"{warn}{persist_note}\n\n"
                    "يلزم توكن البوت من @BotFather لبدء الاستضافة الدائمة."
                )
                await prompt_for_secret(
                    message=message, kind="bot", body=body, user_id=int(uid or 0)
                )
                return ""
            except Exception:
                logger.exception("host secret prompt failed")
        return (
            f"✅ {label} — مربوط بـ `{root}`\n"
            f"• نقطة الدخول: `{entry}`\n"
            f"• العزل المتوقع: {backend}\n"
            f"• المستوى: permanent_host (HostService.start)\n"
            f"{warn}{persist_note}\n\n"
            "أرسل توكن البوت من @BotFather الآن لبدء الاستضافة الدائمة."
        )

    if effect == "post_zip":
        assert root is not None
        try:
            from lumen.bot.helpers import make_zip_from_path
            zip_path = make_zip_from_path(root)
            z = Path(zip_path) if zip_path else None
            if not z or not z.is_file():
                return "تعذر إنشاء ZIP من المشروع."
            with open(z, "rb") as fh:
                await message.reply_document(
                    document=fh,
                    filename=z.name,
                    caption=f"ZIP للمشروع\n`{root}`",
                )
            return f"تم إرسال ZIP ({z.stat().st_size // 1024} KB)."
        except Exception:
            logger.exception("post_zip failed")
            return "فشل إنشاء/إرسال ZIP."

    if effect == "post_preview":
        assert root is not None
        lines = [f"معاينة `{root}` (بدون أسرار):", ""]
        count = 0
        try:
            for dirpath, dirnames, filenames in os.walk(root):
                dirnames[:] = [
                    d for d in dirnames
                    if d not in {".git", "__pycache__", "venv", ".venv", "node_modules"}
                ]
                rel_dir = os.path.relpath(dirpath, root)
                for name in sorted(filenames):
                    if _is_sensitive_name(name):
                        continue
                    if not name.endswith(
                        (".py", ".md", ".txt", ".toml", ".cfg", ".json", ".yml", ".yaml")
                    ):
                        continue
                    rel = name if rel_dir == "." else f"{rel_dir}/{name}"
                    lines.append(f"• `{rel}`")
                    count += 1
                    if count >= 30:
                        break
                if count >= 30:
                    break
            if count == 0:
                lines.append("(لا ملفات قابلة للعرض)")
        except Exception:
            logger.exception("preview failed")
            return "تعذر قراءة المشروع."
        text = "\n".join(lines)[:3500]
        try:
            await message.reply_text(text)
        except Exception:
            await message.reply_text(text.replace("`", ""))
        return f"عرض {count} ملف من المشروع الحقيقي."

    return "إجراء غير معروف."
