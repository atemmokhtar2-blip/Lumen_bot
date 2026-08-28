"""Single CallbackQuery entry — applies engine action then renders with live facts."""
from __future__ import annotations

import logging

from lumen.engine.services.ui_state.controller import apply_action
from lumen.engine.services.ui_state.models import EngineUiPhase
from lumen.engine.services.ui_state.render import render_message

from .facts import gather_ui_facts
from .keyboards import build_inline_keyboard, decode_callback
from .state_store import load_ui_state, persist_ui_session, save_ui_state

logger = logging.getLogger("lumen_bot.ui")


def _help_body() -> str:
    try:
        from lumen.bot.capability_boundaries import get_help_text
        return get_help_text()
    except Exception:
        return "استخدم /help"


async def handle_ui_callback(update, context) -> None:
    q = update.callback_query
    if q is None:
        return
    parsed = decode_callback(q.data or "")
    if parsed is None:
        return
    action_id, arg = parsed
    try:
        await q.answer()
    except Exception:
        pass

    user_data = context.user_data if context.user_data is not None else {}
    state = load_ui_state(user_data)
    result = apply_action(state, action_id, arg)
    save_ui_state(user_data, result.state)

    # Flag for message_router: user should type bot description next
    if result.state.phase == EngineUiPhase.GEN_TYPE and result.state.slots.get("awaiting_text") == "1":
        user_data["engine_ui_await_generate"] = True
    elif result.state.phase == EngineUiPhase.HOME:
        user_data.pop("engine_ui_await_generate", None)

    uid = int(update.effective_user.id) if update.effective_user else 0
    if uid:
        persist_ui_session(uid, dict(user_data))

    facts = gather_ui_facts(uid, user_data)
    if result.state.phase == EngineUiPhase.HELP:
        facts.generate_hint = _help_body()

    text = render_message(result.state, facts)
    if not result.ok:
        text = f"⚠️ {result.message_ar}

{text}"

    try:
        markup = build_inline_keyboard(result.buttons)
        if q.message is not None and getattr(q.message, "text", None) is not None:
            await q.edit_message_text(text=text[:4000], reply_markup=markup)
        elif q.message is not None and getattr(q.message, "caption", None) is not None:
            await q.edit_message_caption(caption=text[:1024], reply_markup=markup)
        else:
            msg = update.effective_message
            if msg:
                await msg.reply_text(text[:4000], reply_markup=markup)
    except Exception:
        logger.exception("ui callback render failed action=%s", action_id)
        try:
            msg = update.effective_message
            if msg:
                await msg.reply_text(text[:4000])
        except Exception:
            pass
