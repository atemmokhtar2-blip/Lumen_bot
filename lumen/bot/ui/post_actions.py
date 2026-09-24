"""Batch 3 — real plane binding for trial / permanent host / zip / preview."""
from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any

from .project_resolve import bind_active_repo, resolve_entry_point, resolve_project_path

logger = logging.getLogger("lumen_bot.ui")

def _merge_host_slots(ud: dict, *, public_url: str = "", instance_id: str = "", kind: str = "", slug: str = "") -> None:
    """Keep engine_ui.slots in sync so GEN_DONE / dashboard buttons see URL."""
    try:
        eu = ud.get("engine_ui")
        if not isinstance(eu, dict):
            eu = {}
            ud["engine_ui"] = eu
        slots = eu.get("slots")
        if not isinstance(slots, dict):
            slots = {}
            eu["slots"] = slots
        if public_url:
            slots["public_url"] = str(public_url)[:300]
        if instance_id:
            slots["host_instance_id"] = str(instance_id)[:128]
        if kind:
            slots["project_kind"] = str(kind)[:32]
        if slug:
            slots["slug"] = str(slug)[:64]
        if not slots.get("delivery_surface"):
            slots["delivery_surface"] = "http_runtime"
        slots["host_mode"] = "http_public"
    except Exception:
        pass



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

def _payload_language(ud: dict) -> str:
    """LanguageRuntime for plane payloads."""
    try:
        eu = ud.get("engine_ui") if isinstance(ud.get("engine_ui"), dict) else {}
        slots = eu.get("slots") if isinstance(eu.get("slots"), dict) else {}
        lang = str(
            slots.get("runtime_language")
            or slots.get("language")
            or ud.get("runtime_language")
            or ud.get("language")
            or "python"
        ).strip().lower()
        if lang in {"ar", "en", "fa", "ur"}:
            return "python"
        return lang or "python"
    except Exception:
        return "python"


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
            # Phase 3: still register in control plane so VPS can attach base later
            try:
                from lumen.engine.services.hosting import get_hosting_service
                eu = ud.get("engine_ui") if isinstance(ud.get("engine_ui"), dict) else {}
                slots = eu.get("slots") if isinstance(eu.get("slots"), dict) else {}
                kind = str(slots.get("project_kind") or "web_api")
                proj = str(root) if root else str(project_ref or "")
                if proj and Path(proj).is_dir():
                    result = get_hosting_service().start_http_public(
                        user_id=int(uid or 0),
                        project_path=proj,
                        project_kind=kind,
                        language=str(slots.get("language") or slots.get("runtime_language") or ud.get("language") or "python"),
                        slug=Path(proj).name,
                        entry_point=str(slots.get("start_command") or ""),
                    )
                    iid = getattr(result.instance, "instance_id", "") if result.instance else ""
                    ud["pending_host"] = {
                        "project_path": proj,
                        "owner_user_id": uid or None,
                        "plane": "http_public",
                        "host_mode": "http_public",
                        "project_kind": kind,
                        "instance_id": iid,
                        "public_url": "",
                    }
                    _merge_host_slots(ud, public_url=str(ud.get("pending_host", {}).get("public_url") or ""), instance_id=str(ud.get("pending_host", {}).get("instance_id") or ""), kind=str(ud.get("pending_host", {}).get("project_kind") or ""), slug=str(ud.get("pending_host", {}).get("slug") or ""))
                    warn = _persist(uid, ud)
                    return (
                        "تم تسجيل المشروع في مستوى التحكم.\n"
                        "لا توجد قاعدة رابط عام (LUMEN_PUBLIC_BASE).\n"
                        "اضبط الدومين على الـ VPS ثم أعد النشر لفتح رابط المتصفح."
                        + warn
                    )
            except Exception as exc:
                logger.exception("artifact_only register failed")
            return (
                "لا توجد قاعدة رابط عام (LUMEN_PUBLIC_BASE).\n"
                "حمّل ZIP أو اضبط الدومين على السيرفر ثم أعد الاستضافة."
            )

        if _surf == "http_runtime":
            try:
                from lumen.engine.core.project_kind import http_runtime_hints, parse_kind
                from lumen.engine.services.hosting import get_hosting_service
                eu = ud.get("engine_ui") if isinstance(ud.get("engine_ui"), dict) else {}
                slots = eu.get("slots") if isinstance(eu.get("slots"), dict) else {}
                kind = str(slots.get("project_kind") or "web_api")
                proj = str(root) if root else str(project_ref or "")
                if not proj or not Path(proj).is_dir():
                    return "مسار المشروع غير موجود — أعد التوليد ثم انشر."
                result = get_hosting_service().start_http_public(
                    user_id=int(uid or 0),
                    project_path=proj,
                    project_kind=kind,
                    slug=Path(proj).name,
                    entry_point=str(slots.get("start_command") or ""),
                )
                inst = result.instance
                public_url = (getattr(inst, "public_url", "") if inst else "") or ""
                health_url = (getattr(inst, "health_url", "") if inst else "") or ""
                ud["pending_host"] = {
                    "project_path": proj,
                    "owner_user_id": uid or None,
                    "plane": "http_public",
                    "host_mode": "http_public",
                    "project_kind": kind,
                    "instance_id": getattr(inst, "instance_id", "") if inst else "",
                    "public_url": public_url,
                    "health_path": getattr(inst, "health_path", "/health") if inst else "/health",
                    "slug": getattr(inst, "slug", "") if inst else "",
                }
                _merge_host_slots(ud, public_url=str(ud.get("pending_host", {}).get("public_url") or ""), instance_id=str(ud.get("pending_host", {}).get("instance_id") or ""), kind=str(ud.get("pending_host", {}).get("project_kind") or ""), slug=str(ud.get("pending_host", {}).get("slug") or ""))
                warn = _persist(uid, ud)
                if not result.ok:
                    return (result.message or "تعذر النشر") + warn
                if public_url:
                    return (
                        f"تم النشر.\n"
                        f"الرابط: {public_url}\n"
                        f"فحص الصحة: {health_url or '/health'}\n"
                        "افتح الرابط في المتصفح."
                        + warn
                    )
                return (result.message or "تم التسجيل — اضبط LUMEN_PUBLIC_BASE") + warn
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

    
    if effect == "post_open_url":
        url = ""
        eu = ud.get("engine_ui") if isinstance(ud.get("engine_ui"), dict) else {}
        slots = eu.get("slots") if isinstance(eu.get("slots"), dict) else {}
        url = str(slots.get("public_url") or ud.get("pending_host", {}).get("public_url") or "").strip()
        if not url:
            # last hosted instance for user
            try:
                from lumen.engine.services.hosting import get_hosting_service
                items = get_hosting_service().list_for_user(int(uid or 0))
                for inst in sorted(items, key=lambda x: float(getattr(x, "started_at", 0) or 0), reverse=True):
                    u = str(getattr(inst, "public_url", "") or getattr(inst, "public_base_url", "") or "")
                    if u.startswith("http"):
                        url = u
                        break
            except Exception:
                pass
        if url.startswith("http"):
            return f"🌐 الرابط:\n{url}\nافتحه في المتصفح."
        return "لا يوجد رابط عام بعد — انشر المشروع أولاً أو اضبط LUMEN_PUBLIC_BASE."

    if effect == "post_logs":
        try:
            from lumen.engine.services.hosting import get_hosting_service
            svc = get_hosting_service()
            iid = ""
            eu = ud.get("engine_ui") if isinstance(ud.get("engine_ui"), dict) else {}
            slots = eu.get("slots") if isinstance(eu.get("slots"), dict) else {}
            iid = str(ud.get("pending_host", {}).get("instance_id") or slots.get("host_instance_id") or "")
            if not iid:
                items = svc.list_for_user(int(uid or 0))
                if items:
                    iid = str(getattr(items[0], "instance_id", "") or "")
            if not iid:
                return "لا يوجد مشروع مستضاف لعرض سجلاته."
            result = svc.logs(user_id=int(uid or 0), instance_id=iid, limit=40)
            return (result.message or "لا سجلات")[:3500]
        except Exception as exc:
            logger.exception("post_logs failed")
            return f"تعذر جلب السجلات: {type(exc).__name__}"

    if effect == "post_stop":
        try:
            from lumen.engine.services.hosting import get_hosting_service
            svc = get_hosting_service()
            iid = str(ud.get("pending_host", {}).get("instance_id") or "")
            if not iid:
                items = svc.list_for_user(int(uid or 0))
                if items:
                    iid = str(getattr(items[0], "instance_id", "") or "")
            if not iid:
                return "لا يوجد مشروع لإيقافه."
            result = svc.stop(instance_id=iid, user_id=int(uid or 0))
            return result.message or ("تم الإيقاف" if result.ok else "تعذر الإيقاف")
        except Exception as exc:
            logger.exception("post_stop failed")
            return f"تعذر الإيقاف: {type(exc).__name__}"


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
