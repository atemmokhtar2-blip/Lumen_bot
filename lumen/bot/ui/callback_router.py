"""CallbackQuery entry — engine actions + optional real generation."""
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
    uid = int(update.effective_user.id) if update.effective_user else 0
    result = apply_action(state, action_id, arg, user_id=uid or None)
    save_ui_state(user_data, result.state)

    if result.state.phase == EngineUiPhase.GEN_TYPE and result.state.slots.get("awaiting_text") == "1":
        user_data["engine_ui_await_generate"] = True
    elif result.state.phase in {EngineUiPhase.HOME, EngineUiPhase.GEN_CONFIRM, EngineUiPhase.GENERATING}:
        if result.state.phase != EngineUiPhase.GEN_TYPE:
            user_data.pop("engine_ui_await_generate", None)

    if uid:
        persist_ui_session(uid, dict(user_data))

    facts = gather_ui_facts(uid, user_data)
    if result.state.phase == EngineUiPhase.HELP:
        facts.generate_hint = _help_body()

    text = render_message(result.state, facts)
    if not result.ok:
        text = "⚠️ " + result.message_ar + "\n\n" + text

    markup = build_inline_keyboard(result.buttons)
    msg = update.effective_message
    try:
        if q.message is not None and getattr(q.message, "text", None) is not None:
            await q.edit_message_text(text=text[:4000], reply_markup=markup)
        elif q.message is not None and getattr(q.message, "caption", None) is not None:
            await q.edit_message_caption(caption=text[:1024], reply_markup=markup)
        elif msg:
            await msg.reply_text(text[:4000], reply_markup=markup)
    except Exception:
        logger.exception("ui callback render failed action=%s", action_id)

    # Real generation — same engine as chat path
    if result.ok and result.run_generation and result.generation_request:
        status = None
        try:
            if msg:
                status = await msg.reply_text("جاري توليد البوت عبر المحرك…")
            from .generate_bridge import run_guided_generation

            gen_result = await run_guided_generation(
                message=msg,
                context=context,
                user=update.effective_user,
                gen_request=result.generation_request,
                status_msg=status or msg,
            )
            st2 = load_ui_state(user_data)
            if gen_result is not None and getattr(gen_result, "success", False):
                st2.phase = EngineUiPhase.GEN_DONE
                st2.project_ref = str(getattr(gen_result, "project_path", "") or "")[:500]
            else:
                st2.phase = EngineUiPhase.GEN_CONFIRM
            save_ui_state(user_data, st2)
            if uid:
                persist_ui_session(uid, dict(user_data))
        except Exception:
            logger.exception("guided generation bridge failed")
