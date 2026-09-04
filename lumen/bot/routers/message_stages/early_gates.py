"""Early gates for Telegram text messages.

Auth, rate-limit, groups, Engine UI slots, cancel, HITL phrases, /plan, tokens.
Each public coroutine returns True when the update is fully handled (caller must return).
"""
from __future__ import annotations

from lumen.bot.helpers import safe_reply_text
import asyncio
import os
from typing import Any

from telegram import Update
from telegram.ext import ContextTypes

from lumen.bot.config import logger
from lumen.bot.helpers import is_allowed, looks_like_bot_token, normalize_bot_token
from lumen.bot.resource_limits import clamp_user_text, MAX_USER_MESSAGE_CHARS
from lumen.bot.middlewares.auth import (
    rate_limit_ok as _rate_limit_ok,
    rate_limit_wait_seconds as _rate_limit_wait_seconds,
)
from lumen.bot.middlewares.mongo_sync import (
    ensure_mongo_user as _ensure_mongo_user,
    mongo_plan_for_user as _mongo_plan_for_user,
    persist_session as _persist_session,
)
from lumen.bot.live import handle_live_run_token, handle_live_deploy_token
from lumen.bot.routers.message_intent import (
    _looks_like_generation_request,
    _is_confirm_phrase,
    _prior_bot_request,
)


async def gate_auth_and_rate(
    *,
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    message,
    user,
) -> bool:
    """False = stop (not allowed / rate limited). True = continue."""
    if not is_allowed(user.id if user else None):
        try:
            await message.reply_text("غير مصرح.")
        except Exception:
            pass
        return False

    # Mongo identity (sync) off event loop
    try:
        await asyncio.to_thread(_ensure_mongo_user, user)
    except Exception:
        logger.exception("ensure_mongo_user failed")

    # Referral: real message = bot use → qualify invitee + notify referrer
    try:
        if user:
            from lumen.application.commands.qualify_referral import QualifyReferralCommand
            from lumen.application.handlers.referral_handlers import handle_qualify_referral

            qres = await asyncio.to_thread(
                handle_qualify_referral,
                QualifyReferralCommand(
                    referred_telegram_id=int(user.id),
                    event="message",
                ),
            )
            if (
                qres
                and getattr(qres, "notify_referrer_id", 0)
                and getattr(qres, "notify_text", "")
            ):
                try:
                    await context.bot.send_message(
                        chat_id=int(qres.notify_referrer_id),
                        text=str(qres.notify_text)[:3500],
                    )
                except Exception:
                    logger.debug("referral notify soft-fail", exc_info=True)
    except Exception:
        logger.debug("referral qualify soft-fail", exc_info=True)

    try:
        allowed = await asyncio.to_thread(_rate_limit_ok, int(user.id) if user else 0)
    except Exception:
        logger.exception("rate_limit_ok failed")
        allowed = True
    if not allowed:
        try:
            wait = await asyncio.to_thread(
                _rate_limit_wait_seconds, int(user.id) if user else 0
            )
            await message.reply_text(
                f"تم تجاوز حد الرسائل. حاول بعد {int(wait) if wait else 30} ثانية."
            )
        except Exception:
            try:
                await message.reply_text("تم تجاوز حد الرسائل. حاول لاحقاً.")
            except Exception:
                pass
        return False
    return True


async def gate_groups(*, update: Update, context, message, user) -> bool:
    """Return False to stop (group message ignored). True = continue."""
    try:
        chat = update.effective_chat
        if chat and getattr(chat, "type", "") in {"group", "supergroup"}:
            text = (message.text or "")
            bot_username = ""
            try:
                me = context.bot
                bot_username = (getattr(me, "username", None) or "") if me else ""
            except Exception:
                pass
            mentioned = bool(bot_username and f"@{bot_username}".lower() in text.lower())
            is_reply = bool(
                message.reply_to_message
                and message.reply_to_message.from_user
                and message.reply_to_message.from_user.id == context.bot.id
            )
            if not mentioned and not is_reply:
                return False
    except Exception:
        logger.exception("group gate failed")
    return True


async def try_engine_ui_text(
    *,
    message,
    context,
    user,
    request: str,
) -> bool:
    """Handle GEN_SLOTS free-text and post-create description. True = handled."""
    from lumen.engine.services.ui_state.models import EngineUiPhase
    from lumen.engine.services.ui_state.controller import (
        apply_action,
        buttons_for_state,
        load_ui_state,
        save_ui_state,
    )
    from lumen.engine.services.ui_state.render import render_message, UiFacts
    from ..ui.keyboards import build_inline_keyboard

    user_data = context.user_data if context else None
    if not user_data or (request or "").startswith("/"):
        return False

    try:
        st = load_ui_state(user_data)
    except Exception:
        return False

    # GEN_SLOTS free text → fill description
    if st.phase == EngineUiPhase.GEN_SLOTS or (
        st.phase == EngineUiPhase.GEN_TYPE and st.slots.get("awaiting_text")
    ):
        try:
            st.slots["bot_description"] = (request or "").strip()[:4000]
            st.slots.pop("awaiting_text", None)
            # move toward confirm / generate
            r = apply_action(st, "to_confirm", "", user_id=int(user.id) if user else 0)
            if r.ok:
                st = r.state
            save_ui_state(user_data, st)
            body = render_message(st, UiFacts())[:2000]
            kb = build_inline_keyboard(buttons_for_state(st), user_id=int(user.id) if user else 0)
            await safe_reply_text(message, body, reply_markup=kb)
            try:
                from lumen.engine.services.ui_state.models import EngineUiPhase as _P
                from lumen.engine.services.ui_state.engine_needs import remaining_needs
                from lumen.bot.ui.input_prompt import ask_text_input
                if st.phase == _P.GEN_SLOTS:
                    rem = remaining_needs(st.needs or [], st.slots)
                    if rem and not (rem[0].choices or []):
                        await ask_text_input(
                            message,
                            kind="slot_answer",
                            body=f"✍️ {rem[0].text}",
                            placeholder=(rem[0].text or "")[:60] or "اكتب إجابتك…",
                        )
                elif st.phase == _P.GEN_TYPE or st.slots.get("awaiting_text") == "1":
                    await ask_text_input(message, kind="bot_description")
            except Exception:
                logger.exception("early_gates ForceReply failed")
            return True
        except Exception:
            logger.exception("engine UI GEN_SLOTS text failed")
            return False

    # After "إنشاء بوت" awaiting description → force generate
    if st.phase in {EngineUiPhase.GEN_TYPE, EngineUiPhase.GEN_CONFIRM} or st.slots.get(
        "awaiting_description"
    ):
        desc = (request or "").strip()
        if len(desc) >= 3:
            try:
                st.slots["bot_description"] = desc[:4000]
                save_ui_state(user_data, st)
                user_data["force_generate_once"] = True
                user_data["last_bot_request"] = desc[:4000]
                # fall through to generation in handle_message
                return False  # not fully handled — generation continues
            except Exception:
                logger.exception("engine UI description capture failed")
    return False


async def try_cancel(*, message, context, request: str) -> bool:
    low = (request or "").strip().lower()
    if low not in {"/cancel", "cancel", "إلغاء", "الغاء", "الغي", "stop", "/stop"}:
        return False
    try:
        if context.user_data is not None:
            context.user_data["cancel_generation"] = True
            context.user_data.pop("force_generate_once", None)
        uid = 0
        try:
            fu = getattr(message, "from_user", None)
            if fu is not None and getattr(fu, "id", None):
                uid = int(fu.id)
        except Exception:
            uid = 0
        # Cooperative cancel — agent_loop polls is_cancelled each step
        if uid:
            try:
                from lumen.engine.services.generation_cancel import request_cancel
                request_cancel(uid)
            except Exception:
                logger.exception("request_cancel failed")
            try:
                from lumen.bot.progress_tracker import clear_generation_busy
                clear_generation_busy(uid)
            except Exception:
                pass
        await message.reply_text("تم إلغاء العملية الحالية. الوكيل هيتوقف عند أقرب خطوة.")
    except Exception:
        logger.exception("cancel failed")
    return True


async def try_bot_token(*, message, context, user, request: str) -> bool:
    if not (looks_like_bot_token(request) or looks_like_bot_token(normalize_bot_token(request))):
        return False
    try:
        tok = normalize_bot_token(request)
        # Retrieve the pending project payload from session state.
        # The delivery flow stores it under multiple keys (pending_run,
        # pending_live_run, pending_deploy) so any token-handler path can find it.
        ud = context.user_data or {}
        pending_run = ud.get("pending_run") or ud.get("pending_live_run") or {}
        pending_deploy = ud.get("pending_deploy") or {}
        # If there is no pending project at all, tell the user instead of crashing.
        if not pending_run and not pending_deploy:
            await message.reply_text(
                "⚠️ لا يوجد مشروع جاهز للتشغيل حالياً.\n"
                "أرسل طلباً لإنشاء بوت أولاً، ثم أرسل التوكن لتشغيله."
            )
            return True
        # handle_live_run_token(message, context, token, pending) — trial chat run
        if pending_run:
            await handle_live_run_token(message, context, tok, pending_run)
            return True
        # handle_live_deploy_token(message, context, token, pending) — permanent host
        if pending_deploy:
            await handle_live_deploy_token(message, context, tok, pending_deploy)
            return True
        return False
    except Exception:
        logger.exception("bot token handling failed")
        return False


__all__ = [
    "gate_auth_and_rate",
    "gate_groups",
    "try_engine_ui_text",
    "try_cancel",
    "try_bot_token",
]
