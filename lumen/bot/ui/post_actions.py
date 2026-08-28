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


def _persist(uid: int, ud: dict) -> None:
    try:
        from lumen.bot.session_store import get_session_store
        if uid:
            get_session_store().save(uid, dict(ud))
    except Exception:
        logger.exception("session persist failed")


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
    root = resolve_project_path(project_ref, ud)
    if root is None and effect in {"post_trial", "post_host", "post_zip", "post_preview"}:
        return "لا يوجد مشروع على القرص — ولّد بوت أو اربط مشروعاً نشطاً أولاً."

    if effect == "post_trial":
        assert root is not None
        entry = resolve_entry_point(root)
        if not (root / entry).is_file() and not any((root / n).is_file() for n in ("main.py", "bot.py")):
            return f"المشروع موجود لكن لا نقطة دخول واضحة تحت `{root}`."
        seconds = _live_seconds(user)
        payload = {
            "project_path": str(root),
            "owner_user_id": uid or None,
            "entry_point": entry,
            "run_seconds": seconds,
            "sandbox": True,
            "plane": "trial_chat",
        }
        ud["pending_run"] = dict(payload)
        ud["pending_live_run"] = dict(payload)
        ud["pending_deploy"] = dict(payload)
        ud.pop("pending_host", None)
        bind_active_repo(ud, root, entry=entry)
        _persist(uid, ud)
        from lumen.engine.services.runtime_planes import RuntimePlane, plane_label_ar
        label = plane_label_ar(RuntimePlane.TRIAL_CHAT)
        return (
            f"✅ {label} — مربوط بـ `{root}`\n"
            f"• نقطة الدخول: `{entry}`\n"
            f"• المدة التقريبية: {seconds // 60} دقيقة\n"
            f"• المستوى: trial_chat (LiveRunner — ليس HostService)\n\n"
            "أرسل توكن البوت من @BotFather الآن لبدء التشغيل التجريبي."
        )

    if effect == "post_host":
        assert root is not None
        entry = resolve_entry_point(root)
        backend = _host_backend_hint()
        ud["pending_host"] = {
            "project_path": str(root),
            "user_id": uid,
            "entry_point": entry,
            "plane": "permanent_host",
            "backend_hint": backend,
        }
        # Token must hit HostService, not trial LiveRunner
        ud.pop("pending_run", None)
        ud.pop("pending_live_run", None)
        ud.pop("pending_deploy", None)
        bind_active_repo(ud, root, entry=entry)
        _persist(uid, ud)
        from lumen.engine.services.runtime_planes import RuntimePlane, plane_label_ar
        label = plane_label_ar(RuntimePlane.PERMANENT_HOST)
        warn = ""
        if "firecracker" in backend and "ready" not in backend and "available" not in backend:
            warn = (
                "\n⚠️ تنبيه: مسار الإنتاج يتطلب Firecracker "
                f"({backend}). على بيئة التطوير قد يُستخدم بديل مصرّح فقط."
            )
        return (
            f"✅ {label} — مربوط بـ `{root}`\n"
            f"• نقطة الدخول: `{entry}`\n"
            f"• العزل المتوقع: {backend}\n"
            f"• المستوى: permanent_host (HostService.start)\n"
            f"{warn}\n\n"
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
