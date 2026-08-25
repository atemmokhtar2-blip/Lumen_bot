"""Hosting start/stop/status/diagnose intents for the consumer bot."""
from __future__ import annotations

import asyncio
from pathlib import Path

from telegram import Update
from telegram.ext import ContextTypes

from ..config import OUTPUT_DIR
from ..helpers import detect_host_intent


async def try_handle_hosting(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    request: str,
    user,
    message,
) -> bool:
    """Return True if this message was fully handled as a hosting intent."""
    # --- Hosting (owner-only foundation; no billing yet) ---
    host_action = detect_host_intent(request)
    if host_action != "none":
        from lumen.engine.services.hosting import get_hosting_service
        svc = get_hosting_service(OUTPUT_DIR)
        uid = message.from_user.id if message.from_user else 0
        active = (context.user_data or {}).get("active_repo") or {}

        if host_action == "start":
            project_path = active.get("path") or ""
            if not project_path or not Path(project_path).exists():
                await message.reply_text(
                    "ما فيش مشروع نشط للاستضافة.\n"
                    "اسحب مستودع أو ولّد بوت أولاً، بعدين اكتب: استضف"
                )
                return True

            context.user_data["pending_host"] = {
                "project_path": project_path,
                "user_id": uid,
            }
            await message.reply_text(
                "🚀 *استضافة المشروع النشط*\n"
                f"• المسار: `{project_path}`\n\n"
                "أرسل الآن توكن البوت من @BotFather لبدء التشغيل الطويل الأمد.\n"
                "(الأساس جاهز — بدون طبقة دفع حالياً)"
            )
            return True


        if host_action == "status":
            result = svc.status(user_id=uid)
            await message.reply_text(result.to_user_text())
            return True


        if host_action == "stop":
            items = svc.list_for_user(uid)
            running = [i for i in items if i.status == "running"]
            if not running:
                await message.reply_text("ما فيش مثيل استضافة شغال لإيقافه.")
                return True

            # stop the most recent running
            target = sorted(running, key=lambda x: x.started_at, reverse=True)[0]
            result = await asyncio.to_thread(
                lambda: svc.stop(instance_id=target.instance_id, user_id=uid)
            )
            await message.reply_text(result.to_user_text())
            return True


        if host_action == "diagnose":
            items = svc.list_for_user(uid)
            if not items:
                await message.reply_text("ما فيش مثيلات لتشخيصها.")
                return True

            target = sorted(items, key=lambda x: x.started_at, reverse=True)[0]
            result = await asyncio.to_thread(
                lambda: svc.diagnose(user_id=uid, instance_id=target.instance_id)
            )
            await message.reply_text(result.to_user_text())
            return True


    return False
