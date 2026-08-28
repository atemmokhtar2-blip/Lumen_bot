"""CallbackQuery entry — engine actions + optional real generation."""
from __future__ import annotations

import logging

from lumen.engine.services.ui_state.controller import apply_action
from lumen.engine.services.ui_state.models import EngineUiPhase
# Bound once at module level — never re-import as `render_message` inside
# handlers (that causes UnboundLocalError: "cannot access local variable
# 'render_message' where it is not associated with a value").
from lumen.engine.services.ui_state.render import render_message as render_ui_message

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


async def _safe_render_ui(q, msg, text: str, markup, *, user_data=None, context=None) -> None:
    """Single-surface UI: edit in place, then hard-prune chat to max 2 bot messages."""
    from .chat_hygiene import send_or_edit_ui

    bot = getattr(context, "bot", None) if context is not None else None
    chat_id = None
    preferred = None
    if q is not None and getattr(q, "message", None) is not None:
        preferred = q.message
        chat_id = getattr(q.message.chat, "id", None)
    elif msg is not None:
        preferred = msg
        chat_id = getattr(getattr(msg, "chat", None), "id", None)
    if bot is None and preferred is not None:
        bot = getattr(preferred, "get_bot", lambda: None)()
    if chat_id is None:
        # last resort legacy path
        try:
            if preferred is not None and getattr(preferred, "text", None):
                await preferred.edit_text(text=(text or "")[:4000], reply_markup=markup)
                return
            if preferred is not None:
                await preferred.reply_text((text or "")[:4000], reply_markup=markup)
        except Exception:
            logger.exception("legacy render failed")
        return
    await send_or_edit_ui(
        bot=bot,
        chat_id=int(chat_id),
        user_data=user_data,
        text=text,
        markup=markup,
        preferred_message=preferred,
    )


async def handle_ui_callback(update, context) -> None:
    """Top-level UI callback — answer first, never hang on Redis/DB."""
    q = update.callback_query
    if q is None:
        return

    import asyncio

    user = update.effective_user
    uid = int(user.id) if user else 0

    # 0) Acknowledge IMMEDIATELY — stops Telegram loading spinner (best practice)
    try:
        await q.answer()
    except Exception:
        pass

    # 1) Identity
    try:
        from lumen.bot.helpers import is_allowed
        if not uid or not is_allowed(uid):
            return
    except Exception:
        logger.exception("auth check failed on callback")
        return

    # 2) Signed parse + closed catalog
    parsed = decode_callback(q.data or "", user_id=uid)
    if parsed is None:
        # Stale / unsigned / foreign button — silent fail-closed
        return
    action_id, arg = parsed
    try:
        from lumen.engine.services.ui_state.catalog import is_known_action
        if not is_known_action(action_id):
            logger.warning("unknown ui action rejected uid=%s action=%s", uid, action_id)
            return
    except Exception:
        logger.exception("catalog check failed")
        return

    # 3) Rate limit with hard timeout (never block UI on Redis stall)
    try:
        from lumen.bot.middlewares.auth import rate_limit_ok
        ok = await asyncio.wait_for(asyncio.to_thread(rate_limit_ok, uid), timeout=1.5)
        if not ok:
            try:
                await q.answer("انتظر قليلاً", show_alert=False)
            except Exception:
                pass
            return
    except Exception:
        logger.debug("callback rate limit skipped", exc_info=True)

    try:
        await asyncio.wait_for(
            _handle_ui_callback_body(update, context, q, action_id, arg),
            timeout=25.0,
        )
    except asyncio.TimeoutError:
        logger.error("ui callback timeout action=%s uid=%s", action_id, uid)
        try:
            msg = update.effective_message or (q.message if q else None)
            if msg is not None:
                await msg.reply_text("استغرق الرد وقتاً أطول من المعتاد. جرّب مرة أخرى.")
        except Exception:
            pass
    except Exception as exc:
        logger.exception(
            "ui callback fatal action=%s arg=%s err=%s:%s",
            action_id,
            arg,
            type(exc).__name__,
            str(exc)[:200],
        )



async def _handle_ui_callback_body(update, context, q, action_id: str, arg: str) -> None:
    # One-shot welcome photo: delete permanently on first button press
    try:
        ud0 = context.user_data if context.user_data is not None else {}
        wmid = ud0.get("lumen_welcome_msg_id")
        if wmid and update.effective_chat:
            try:
                await context.bot.delete_message(
                    chat_id=int(update.effective_chat.id),
                    message_id=int(wmid),
                )
            except Exception:
                pass
            ud0.pop("lumen_welcome_msg_id", None)
            ud0["lumen_welcome_shown"] = True
            # Drop from hygiene tracker so it is never edited again
            try:
                ids = list(ud0.get("lumen_bot_ui_msg_ids") or [])
                ud0["lumen_bot_ui_msg_ids"] = [i for i in ids if int(i) != int(wmid)]
            except Exception:
                pass
    except Exception:
        pass

    user_data = context.user_data if context.user_data is not None else {}
    # Ensure PTB keeps the same dict when user_data was None
    if context.user_data is None:
        try:
            context.user_data = user_data
        except Exception:
            pass

    state = load_ui_state(user_data)
    uid = int(update.effective_user.id) if update.effective_user else 0
    result = apply_action(state, action_id, arg, user_id=uid or None)

    # Batch 4: bind live host instances into state slots for dynamic buttons
    if result.state.phase.value == "dashboard":
        try:
            from .dash_actions import sync_dashboard_slots
            from lumen.engine.services.ui_state.controller import ApplyResult, buttons_for_state

            result.state.slots = sync_dashboard_slots(uid, result.state.slots)
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

    # Persist off the event loop (SQLite can block under load)
    if uid:
        try:
            import asyncio
            asyncio.get_running_loop().create_task(
                asyncio.to_thread(persist_ui_session, uid, dict(user_data))
            )
        except Exception:
            try:
                persist_ui_session(uid, dict(user_data))
            except Exception:
                pass

    # Facts I/O (Neon/Mongo) off event loop — include hosts only for dashboard
    include_hosts = result.state.phase.value == "dashboard"
    if action_id in {"open_billing", "open_dashboard", "home", "open_generate"}:
        try:
            from .facts import invalidate_facts_cache
            invalidate_facts_cache(uid)
        except Exception:
            pass
    try:
        import asyncio
        from functools import partial
        facts = await asyncio.wait_for(
            asyncio.to_thread(
                partial(gather_ui_facts, uid, user_data, include_hosts=include_hosts)
            ),
            timeout=8.0,
        )
    except Exception:
        try:
            facts = gather_ui_facts(uid, user_data, include_hosts=include_hosts)
        except TypeError:
            facts = gather_ui_facts(uid, user_data)
    if result.state.phase == EngineUiPhase.HELP:
        facts.generate_hint = _help_body()

    text = render_ui_message(result.state, facts)
    if not result.ok:
        text = "⚠️ " + result.message_ar + "\n\n" + text

    try:
        markup = build_inline_keyboard(result.buttons, user_id=uid)
    except Exception:
        logger.exception("build_inline_keyboard failed action=%s", action_id)
        markup = None

    msg = update.effective_message
    await _safe_render_ui(q, msg, text, markup, user_data=user_data, context=context)

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
            if st2.phase in {EngineUiPhase.CONTEXT, EngineUiPhase.GEN_DONE} and msg:
                from lumen.engine.services.ui_state.controller import buttons_for_state
                if st2.phase == EngineUiPhase.GEN_DONE:
                    body = (
                        "ما التالي؟\n"
                        "• تجربة في الشات — تشغيل مؤقت\n"
                        "• استضافة دائمة — Firecracker\n"
                        "• ZIP أو معاينة"
                    )
                else:
                    body = render_ui_message(st2)[:2000]
                await _safe_render_ui(
                    q, msg, body,
                    build_inline_keyboard(buttons_for_state(st2), user_id=uid),
                    user_data=user_data, context=context,
                )
        except Exception:
            logger.exception("guided generation bridge failed")
            if msg is not None:
                try:
                    await msg.reply_text(
                        "❌ فشل التوليد من الواجهة. أعد المحاولة أو اكتب وصف البوت كنص."
                    )
                except Exception:
                    pass

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
                # Merge into the same UI surface — never flood chat
                merged = (text + "\n\n" + note)[:4000] if text else note[:4000]
                await _safe_render_ui(
                    q, msg, merged, markup, user_data=user_data, context=context
                )
        except Exception:
            logger.exception("post_side_effect failed effect=%s", result.post_side_effect)

    if result.ok and action_id == "open_dashboard" and msg:
        # Status already reflected in dashboard render + hosts facts — no extra spam message
        pass

    if result.ok and getattr(result, "dash_effect", ""):
        try:
            from .dash_actions import execute_dash_effect
            from lumen.engine.services.ui_state.controller import buttons_for_state

            note = await execute_dash_effect(
                effect=result.dash_effect,
                target=result.dash_target,
                user_id=uid,
                user_data=user_data,
                message=msg,
            )
            if result.dash_effect == "dash_stop":
                from .dash_actions import sync_dashboard_slots
                st = load_ui_state(user_data)
                st.slots = sync_dashboard_slots(uid, st.slots)
                save_ui_state(user_data, st)
                body = render_ui_message(
                    st, gather_ui_facts(uid, user_data, include_hosts=True)
                )
                await _safe_render_ui(
                    q, msg, body,
                    build_inline_keyboard(buttons_for_state(st), user_id=uid),
                    user_data=user_data, context=context,
                )
            elif note and msg:
                merged = ((text or "") + "\n\n" + note)[:4000]
                await _safe_render_ui(
                    q, msg, merged, markup, user_data=user_data, context=context
                )
        except Exception:
            logger.exception("dash_effect failed effect=%s", result.dash_effect)
