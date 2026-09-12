"""Billing-related callback side effects (Stars invoice, etc.)."""
from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger("lumen_bot.ui.callbacks.billing")


async def handle_buy_pro_plan(
    *,
    action_id: str,
    result: Any,
    update: Any,
    context: Any,
    q: Any,
    msg: Any,
    uid: int,
) -> bool:
    """Send Telegram Stars invoice for Pro. Returns True if handled (caller should return)."""
    if not (getattr(result, "ok", False) and action_id == "buy_pro_plan"):
        return False
    try:
        from lumen.engine.services.ui_state.pro_plan import (
            PRO_PLAN_TITLE,
            PRO_PLAN_PRICE_STARS,
            PRO_PLAN_INVOICE_PAYLOAD,
            pro_plan_invoice_description,
        )
        from telegram import LabeledPrice

        bot = getattr(context, "bot", None)
        chat_id = None
        if q is not None and getattr(q, "message", None) is not None:
            chat_id = getattr(q.message.chat, "id", None)
        elif msg is not None:
            chat_id = getattr(getattr(msg, "chat", None), "id", None)
        if bot is not None and chat_id is not None:
            await bot.send_invoice(
                chat_id=int(chat_id),
                title=PRO_PLAN_TITLE,
                description=pro_plan_invoice_description(),
                payload=PRO_PLAN_INVOICE_PAYLOAD,
                currency="XTR",
                prices=[LabeledPrice(label=PRO_PLAN_TITLE, amount=PRO_PLAN_PRICE_STARS)],
                provider_token="",
            )
            logger.info(
                "Stars invoice sent uid=%s chat=%s amount=%s",
                uid,
                chat_id,
                PRO_PLAN_PRICE_STARS,
            )
            return True
        logger.warning("buy_pro_plan: bot or chat_id missing uid=%s", uid)
    except Exception:
        logger.exception("buy_pro_plan invoice failed uid=%s", uid)
    return False


__all__ = ["handle_buy_pro_plan"]
