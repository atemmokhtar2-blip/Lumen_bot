"""Batch 3 — execute post-generation UI side effects on real planes."""
from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any

logger = logging.getLogger("lumen_bot.ui")

_SECRET_NAME_PARTS = (
    "token", "secret", "password", "credential", ".env", "api_key", "private",
)


def _is_sensitive_name(name: str) -> bool:
    low = name.lower()
    return any(p in low for p in _SECRET_NAME_PARTS)


async def execute_post_side_effect(
    *,
    effect: str,
    project_ref: str,
    message,
    context,
    user,
) -> str:
    """Return Arabic status line after attempting the effect."""
    effect = (effect or "").strip()
    root = Path(project_ref) if project_ref else None
    uid = int(user.id) if user else 0
    ud = context.user_data if context.user_data is not None else {}

    if effect == "post_trial":
        if not root or not root.is_dir():
            return "مسار المشروع غير موجود للتجربة."
        payload = {
            "project_path": str(root),
            "owner_user_id": uid or None,
            "entry_point": "main.py",
            "run_seconds": int(os.environ.get("LIVE_RUN_SECONDS", "1800") or 1800),
            "sandbox": True,
            "plane": "trial_chat",
        }
        ud["pending_run"] = dict(payload)
        ud["pending_live_run"] = dict(payload)
        ud["pending_deploy"] = dict(payload)
        ud.pop("pending_host", None)
        try:
            from lumen.bot.session_store import get_session_store
            if uid:
                get_session_store().save(uid, dict(ud))
        except Exception:
            logger.exception("persist trial pending failed")
        return (
            "وضع التجربة (شات مؤقت) جاهز.\n"
            "أرسل توكن البوت من @BotFather الآن.\n"
            "هذه تجربة قصيرة — ليست استضافة دائمة."
        )

    if effect == "post_host":
        if not root or not root.is_dir():
            return "مسار المشروع غير موجود للاستضافة."
        ud["pending_host"] = {
            "project_path": str(root),
            "user_id": uid,
            "plane": "permanent_host",
        }
        # Clear trial pending so token routes to host path first
        ud.pop("pending_run", None)
        ud.pop("pending_live_run", None)
        ud.pop("pending_deploy", None)
        try:
            from lumen.bot.session_store import get_session_store
            if uid:
                get_session_store().save(uid, dict(ud))
        except Exception:
            logger.exception("persist host pending failed")
        return (
            "وضع الاستضافة الدائمة جاهز.\n"
            "أرسل توكن البوت من @BotFather.\n"
            "التشغيل عبر مسار Firecracker المعزول (ليس تجربة الشات)."
        )

    if effect == "post_zip":
        if not root or not root.is_dir():
            return "لا يمكن إنشاء ZIP — المسار غير موجود."
        try:
            from lumen.bot.helpers import make_zip_from_path
            zip_path = make_zip_from_path(root)
            if not zip_path or not Path(zip_path).is_file():
                return "تعذر إنشاء ملف ZIP."
            with open(zip_path, "rb") as fh:
                await message.reply_document(
                    document=fh,
                    filename=Path(zip_path).name,
                    caption="مشروع البوت (ZIP).",
                )
            return "تم إرسال ZIP."
        except Exception:
            logger.exception("post_zip failed")
            return "فشل إرسال ZIP — راجع السجلات."

    if effect == "post_preview":
        if not root or not root.is_dir():
            return "لا مسار للمعاينة."
        lines = ["معاينة الملفات (بدون أسرار):", ""]
        count = 0
        try:
            for dirpath, dirnames, filenames in os.walk(root):
                dirnames[:] = [d for d in dirnames if d not in {".git", "__pycache__", "venv", ".venv", "node_modules"}]
                rel_dir = os.path.relpath(dirpath, root)
                for name in sorted(filenames):
                    if _is_sensitive_name(name):
                        continue
                    if not name.endswith((".py", ".md", ".txt", ".toml", ".cfg", ".json", ".yml", ".yaml")):
                        continue
                    rel = name if rel_dir == "." else f"{rel_dir}/{name}"
                    lines.append(f"• `{rel}`")
                    count += 1
                    if count >= 25:
                        break
                if count >= 25:
                    break
            if count == 0:
                lines.append("(لا ملفات قابلة للعرض)")
        except Exception:
            logger.exception("preview walk failed")
            return "تعذر قراءة ملفات المشروع."
        try:
            await message.reply_text("\n".join(lines)[:3500])
        except Exception:
            await message.reply_text("\n".join(lines)[:3500].replace("`", ""))
        return f"عرض {count} ملف."

    return "إجراء غير معروف."
