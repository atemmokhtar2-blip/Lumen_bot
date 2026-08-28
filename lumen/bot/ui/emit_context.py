"""Emit Batch 6 contextual UI (state + keyboard) from any failure path."""
from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger("lumen_bot.ui")


async def emit_context_event(
    *,
    message,
    context,
    user,
    kind: str,
    detail: str = "",
    also_edit=None,
) -> None:
    """Persist CONTEXT phase and send smart buttons. Best-effort, never raises out."""
    try:
        from lumen.engine.services.ui_state.ui_events import UiEventKind, apply_event, event_label_ar
        from lumen.engine.services.ui_state.controller import buttons_for_state
        from lumen.engine.services.ui_state.render import render_message
        from lumen.bot.ui.keyboards import build_inline_keyboard
        from lumen.bot.ui.state_store import load_ui_state, save_ui_state, persist_ui_session

        ud = context.user_data if context.user_data is not None else {}
        st = load_ui_state(ud)
        try:
            k = UiEventKind(str(kind))
        except ValueError:
            k = UiEventKind.GENERATION_FAILED
        st = apply_event(st, k, detail=detail or "")
        # Keep last description for retry_generate
        save_ui_state(ud, st)
        uid = int(getattr(user, "id", 0) or 0)
        if uid:
            persist_ui_session(uid, dict(ud))

        body = render_message(st)
        markup = build_inline_keyboard(buttons_for_state(st))
        text = body[:3500]
        if also_edit is not None:
            try:
                from lumen.bot.helpers import safe_edit_text
                await safe_edit_text(also_edit, text)
            except Exception:
                pass
            try:
                await also_edit.edit_reply_markup(reply_markup=markup)
            except Exception:
                if message is not None:
                    await message.reply_text(text, reply_markup=markup)
        elif message is not None:
            from lumen.bot.ui.chat_hygiene import send_or_edit_ui
            chat_id = getattr(getattr(message, "chat", None), "id", None)
            bot = getattr(context, "bot", None) or getattr(message, "get_bot", lambda: None)()
            if chat_id and bot:
                await send_or_edit_ui(
                    bot=bot,
                    chat_id=int(chat_id),
                    user_data=ud,
                    text=text,
                    markup=markup,
                    preferred_message=message,
                )
            else:
                await message.reply_text(text, reply_markup=markup)
    except Exception:
        logger.exception("emit_context_event failed kind=%s", kind)


def classify_host_failure(message: str) -> str:
    low = (message or "").lower()
    if "حد" in message or "limit" in low or "quota" in low or "hosted" in low:
        return "host_limit"
    if "firecracker" in low or "عزل" in message or "sandbox" in low:
        return "sandbox_unavailable"
    if "مسار" in message or "غير موجود" in message or "خارج" in message:
        return "no_project"
    return "host_failed"
