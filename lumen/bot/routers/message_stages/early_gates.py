"""Early gates for Telegram text messages.

Auth, rate-limit, groups, Engine UI slots, cancel, HITL phrases, /plan, tokens.
Each public coroutine returns True when the update is fully handled (caller must return).
"""
from __future__ import annotations

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
    _free_agent_mode,
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
            await message.reply_text(body, reply_markup=kb)
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
                user_data["engine_direct_request"] = desc[:4000]
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
        await message.reply_text("تم إلغاء العملية الحالية.")
    except Exception:
        logger.exception("cancel failed")
    return True


async def try_bot_token(*, message, context, user, request: str) -> bool:
    if not (looks_like_bot_token(request) or looks_like_bot_token(normalize_bot_token(request))):
        return False
    try:
        tok = normalize_bot_token(request)
        handled = await handle_live_run_token(message, context, user, tok)
        if handled:
            return True
        handled = await handle_live_deploy_token(message, context, user, tok)
        return bool(handled)
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
