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
    # Batch 4: bind live host instances into state slots for dynamic buttons
    if result.state.phase.value == "dashboard":
        try:
            from .dash_actions import sync_dashboard_slots
            from lumen.engine.services.ui_state.controller import buttons_for_state
            result.state.slots = sync_dashboard_slots(uid, result.state.slots)
            # refresh buttons after sync
            from lumen.engine.services.ui_state.controller import ApplyResult
            result = ApplyResult(
                state=result.state,
                ok=result.ok,
                message_ar=result.message_ar,
                buttons=buttons_for_state(result.state),
                run_generation=result.run_generation,
                generation_request=result.generation_request,
                post_side_effect=result.post_side_effect,
                dash_effect=result.dash_effect,
                dash_target=result.dash_target,
            )
        except Exception:
            logger.exception("dashboard slot sync failed")
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
                from lumen.engine.services.ui_state.ui_events import UiEventKind, apply_event
                err = ""
                try:
                    errs = list(getattr(gen_result, "errors", None) or [])
                    err = str(errs[0])[:300] if errs else "generation_failed"
                except Exception:
                    err = "generation_failed"
                st2 = apply_event(st2, UiEventKind.GENERATION_FAILED, detail=err)
            save_ui_state(user_data, st2)
            if uid:
                persist_ui_session(uid, dict(user_data))
            if st2.phase == EngineUiPhase.CONTEXT and msg:
                from lumen.engine.services.ui_state.controller import buttons_for_state
                from lumen.engine.services.ui_state.render import render_message
                await msg.reply_text(
                    render_message(st2)[:2000],
                    reply_markup=build_inline_keyboard(buttons_for_state(st2)),
                )
            if st2.phase == EngineUiPhase.GEN_DONE and msg:
                from lumen.engine.services.ui_state.controller import buttons_for_state
                body = (
                    "ما التالي؟\n"
                    "• تجربة في الشات — تشغيل مؤقت\n"
                    "• استضافة دائمة — Firecracker\n"
                    "• ZIP أو معاينة"
                )
                await msg.reply_text(
                    body,
                    reply_markup=build_inline_keyboard(buttons_for_state(st2)),
                )
        except Exception:
            logger.exception("guided generation bridge failed")

    if result.ok and getattr(result, "post_side_effect", ""):
        try:
            from .post_actions import execute_post_side_effect
            from .project_resolve import resolve_project_path
            pref = result.state.project_ref
            if not pref:
                rp = resolve_project_path("", user_data)
                pref = str(rp) if rp else ""
                if pref:
                    result.state.project_ref = pref
                    save_ui_state(user_data, result.state)
            note = await execute_post_side_effect(
                effect=result.post_side_effect,
                project_ref=pref,
                message=msg,
                context=context,
                user=update.effective_user,
            )
            if note and msg:
                await msg.reply_text(note[:2000])
        except Exception:
            logger.exception("post_side_effect failed effect=%s", result.post_side_effect)

    if result.ok and action_id == "open_dashboard" and msg:
        try:
            from .dash_actions import execute_dash_effect
            overview = await execute_dash_effect(
                effect="dash_status",
                target="all",
                user_id=uid,
                user_data=user_data,
                message=msg,
            )
            if overview:
                await msg.reply_text(("ملخص الاستضافة:\n" + overview)[:3500])
        except Exception:
            logger.exception("dashboard overview failed")

    if result.ok and getattr(result, "dash_effect", ""):
        try:
            from .dash_actions import execute_dash_effect
            note = await execute_dash_effect(
                effect=result.dash_effect,
                target=result.dash_target,
                user_id=uid,
                user_data=user_data,
                message=msg,
            )
            if note and msg:
                await msg.reply_text(note[:3500])
            # re-sync hosts after stop
            if result.dash_effect == "dash_stop":
                from .dash_actions import sync_dashboard_slots
                from lumen.engine.services.ui_state.controller import buttons_for_state
                st = load_ui_state(user_data)
                st.slots = sync_dashboard_slots(uid, st.slots)
                save_ui_state(user_data, st)
                if msg:
                    await msg.reply_text(
                        "تم تحديث القائمة.",
                        reply_markup=build_inline_keyboard(buttons_for_state(st)),
                    )
        except Exception:
            logger.exception("dash_effect failed effect=%s", result.dash_effect)
