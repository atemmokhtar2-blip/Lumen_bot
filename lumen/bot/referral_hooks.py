"""Single entry for referral qualification from any bot surface."""
from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger("lumen_bot.referral_hooks")


async def qualify_bot_use(context: Any, user_id: int | None, event: str) -> None:
    """Mark invitee as having used the bot; notify referrer when needed.

    Safe no-op when user was not referred or event is not bot-use.
    """
    try:
        uid = int(user_id or 0)
    except (TypeError, ValueError):
        return
    if uid <= 0:
        return
    try:
        import asyncio
        from lumen.application.commands.qualify_referral import QualifyReferralCommand
        from lumen.application.handlers.referral_handlers import handle_qualify_referral

        qres = await asyncio.to_thread(
            handle_qualify_referral,
            QualifyReferralCommand(referred_telegram_id=uid, event=str(event or "")),
        )
        if not qres:
            return
        rid = int(getattr(qres, "notify_referrer_id", 0) or 0)
        text = str(getattr(qres, "notify_text", "") or "").strip()
        if not rid or not text:
            return
        bot = getattr(context, "bot", None)
        if bot is None:
            return
        try:
            await bot.send_message(chat_id=rid, text=text[:3500])
        except Exception:
            logger.debug("referral notify failed", exc_info=True)
    except Exception:
        logger.debug("qualify_bot_use soft-fail", exc_info=True)
