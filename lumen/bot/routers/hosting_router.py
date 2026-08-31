"""Hosting start/stop/status/diagnose intents for the consumer bot.

All paths bind to HostService (not trial LiveRunner).
Status/stop/diagnose attach the persistent host panel when possible.
"""
from __future__ import annotations

import asyncio
from pathlib import Path

from telegram import Update
from telegram.ext import ContextTypes

from ..config import OUTPUT_DIR, logger
from ..helpers import detect_host_intent
from lumen.bot.helpers import safe_reply_text


async def try_handle_hosting(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    request: str,
    user,
    message,
) -> bool:
    """Return True if this message was fully handled as a hosting intent."""
    host_action = detect_host_intent(request)
    if host_action == "none":
        return False

    try:
        from lumen.engine.services.hosting import get_hosting_service
        svc = get_hosting_service(OUTPUT_DIR)
    except Exception as exc:
        logger.exception("HostService unavailable")
        await safe_reply_text(message, 
            "❌ خدمة الاستضافة غير متاحة حالياً.\n"
            f"• السبب: {type(exc).__name__}\n"
            "• تأكد من DATABASE_URL أو ENVIRONMENT=dev."
        )
        return True

    uid = message.from_user.id if message.from_user else 0
    active = (context.user_data or {}).get("active_repo") or {}

    if host_action == "start":
        project_path = active.get("path") or ""
        if not project_path or not Path(project_path).exists():
            await safe_reply_text(message, 
                "ما فيش مشروع نشط للاستضافة.\n"
                "اسحب مستودع أو ولّد بوت أولاً، بعدين اكتب: استضف"
            )
            return True

        context.user_data["pending_host"] = {
            "project_path": project_path,
            "user_id": uid,
        }
        try:
            from lumen.bot.ui.secret_prompt import prompt_for_secret
            from lumen.bot.ui.rtl_text import code_path

            body = (
                "🚀 استضافة المشروع النشط (HostService / Firecracker)\n"
                f"• المسار: {code_path(project_path)}\n\n"
                "يلزم توكن البوت من @BotFather."
            )
            await prompt_for_secret(
                message=message, kind="bot", body=body, user_id=int(uid or 0)
            )
        except Exception:
            await safe_reply_text(message, 
                "🚀 أرسل توكن البوت من @BotFather.\n"
                "بعد الإرسال سيُحذف سرك من المحادثة."
            )
        return True

    if host_action == "status":
        result = await asyncio.to_thread(lambda: svc.status(user_id=uid))
        text = result.to_user_text() if hasattr(result, "to_user_text") else str(result)
        try:
            from lumen.bot.ui.host_panel import host_panel_buttons
            from lumen.bot.ui.keyboards import build_inline_keyboard

            markup = build_inline_keyboard(
                host_panel_buttons(instance_index="0"), user_id=int(uid or 0)
            )
            # Keep phase dashboard for subsequent dash_* clicks
            try:
                from lumen.bot.ui.state_store import load_ui_state, save_ui_state
                from lumen.bot.ui.dash_actions import sync_dashboard_slots
                from lumen.engine.services.ui_state.models import EngineUiPhase

                st = load_ui_state(context.user_data)
                st.slots = sync_dashboard_slots(int(uid or 0), dict(st.slots or {}))
                st.phase = EngineUiPhase.DASHBOARD
                save_ui_state(context.user_data, st)
            except Exception:
                pass
            await safe_reply_text(message, str(text)[:3500], reply_markup=markup)
        except Exception:
            await safe_reply_text(message, str(text)[:3500])
        return True

    if host_action == "stop":
        items = list(svc.list_for_user(uid))
        running = [i for i in items if getattr(i, "status", "") == "running"]
        if not running:
            await safe_reply_text(message, "ما فيش مثيل استضافة شغال لإيقافه.")
            return True
        target = sorted(
            running, key=lambda x: float(getattr(x, "started_at", 0) or 0), reverse=True
        )[0]
        result = await asyncio.to_thread(
            lambda: svc.stop(instance_id=target.instance_id, user_id=uid)
        )
        text = result.to_user_text() if hasattr(result, "to_user_text") else str(result)
        try:
            from lumen.bot.ui.host_panel import host_panel_buttons
            from lumen.bot.ui.keyboards import build_inline_keyboard

            markup = build_inline_keyboard(
                host_panel_buttons(instance_index="0"), user_id=int(uid or 0)
            )
            await safe_reply_text(message, str(text)[:3500], reply_markup=markup)
        except Exception:
            await safe_reply_text(message, str(text)[:3500])
        return True

    if host_action == "diagnose":
        items = list(svc.list_for_user(uid))
        if not items:
            await safe_reply_text(message, "ما فيش مثيلات لتشخيصها.")
            return True
        target = sorted(
            items, key=lambda x: float(getattr(x, "started_at", 0) or 0), reverse=True
        )[0]
        result = await asyncio.to_thread(
            lambda: svc.diagnose(user_id=uid, instance_id=target.instance_id)
        )
        text = result.to_user_text() if hasattr(result, "to_user_text") else str(result)
        try:
            from lumen.bot.ui.host_panel import host_panel_buttons
            from lumen.bot.ui.keyboards import build_inline_keyboard

            markup = build_inline_keyboard(
                host_panel_buttons(instance_index="0"), user_id=int(uid or 0)
            )
            await safe_reply_text(message, str(text)[:3500], reply_markup=markup)
        except Exception:
            await safe_reply_text(message, str(text)[:3500])
        return True

    return False
