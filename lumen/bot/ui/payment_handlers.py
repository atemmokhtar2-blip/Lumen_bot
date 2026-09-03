"""Telegram Stars (XTR) payment handlers — in-Telegram only.

  - pre_checkout_query: must answer within 10s or Telegram cancels the invoice.
  - successful_payment: grant the Pro plan subscription on confirmed payment.
"""
from __future__ import annotations

import logging

logger = logging.getLogger("lumen_bot.ui.payments")


async def handle_pre_checkout(update, context) -> None:
    """Answer pre_checkout_query — accept all XTR (Stars) payments for Pro.

    Telegram Stars payments are provider-less; we just need to answer ok=True
    within 10 seconds or Telegram auto-cancels the invoice.
    """
    pcq = update.pre_checkout_query
    if pcq is None:
        return
    try:
        await pcq.answer(ok=True)
    except Exception:
        logger.exception("pre_checkout answer failed id=%s", getattr(pcq, "id", "?"))


async def handle_successful_payment(update, context) -> None:
    """Grant the Lumen Pro subscription after a confirmed Stars payment.

    The user's successful_payment.message contains:
      - currency: "XTR"
      - total_amount: star amount
      - invoice_payload: our PRO_PLAN_INVOICE_PAYLOAD
      - telegram_payment_charge_id: charge ID for refunds
    """
    msg = update.effective_message
    if msg is None or not getattr(msg, "successful_payment", None):
        return
    sp = msg.successful_payment
    uid = int(getattr(update.effective_user, "id", 0) or 0)

    from lumen.engine.services.ui_state.pro_plan import (
        PRO_PLAN_ID,
        PRO_PLAN_INVOICE_PAYLOAD,
        PRO_PLAN_PRICE_STARS,
    )

    payload = getattr(sp, "invoice_payload", "") or ""
    currency = getattr(sp, "currency", "") or ""
    amount = int(getattr(sp, "total_amount", 0) or 0)

    # Verify this is our Pro plan invoice — payload + currency + exact amount
    if payload != PRO_PLAN_INVOICE_PAYLOAD or currency != "XTR" or amount != PRO_PLAN_PRICE_STARS:
        logger.warning(
            "successful_payment mismatch payload=%s currency=%s amount=%s expected=%s uid=%s",
            payload, currency, amount, PRO_PLAN_PRICE_STARS, uid,
        )
        return

    logger.info(
        "Pro plan purchased uid=%s stars=%s charge=%s",
        uid,
        amount,
        getattr(sp, "telegram_payment_charge_id", "?"),
    )

    # Grant the subscription — record in user_data + best-effort persistent store
    user_data = context.user_data if context.user_data is not None else {}
    try:
        from datetime import datetime, timedelta, timezone
        now = datetime.now(timezone.utc)
        user_data["pro_plan"] = {
            "plan_id": PRO_PLAN_ID,
            "started_at": now.isoformat(),
            "expires_at": (now + timedelta(days=30)).isoformat(),
            "stars_paid": amount,
            "charge_id": getattr(sp, "telegram_payment_charge_id", ""),
        }
    except Exception:
        logger.exception("failed to record pro_plan in user_data uid=%s", uid)

    # Best-effort: persist to session store
    try:
        from lumen.bot.ui.state_store import persist_ui_session
        persist_ui_session(uid, dict(user_data))
    except Exception:
        logger.debug("session persist skipped for pro_plan uid=%s", uid, exc_info=True)

    # Acknowledge to the user
    try:
        await msg.reply_text(
            "✅ تم تفعيل اشتراك Lumen Pro بنجاح!\n\n"
            "🚀 استمتع بـ:\n"
            "• 2 GB تخزين\n"
            "• 512 MB RAM\n"
            "• 0.5 CPU\n"
            "• حتى 3 بوتات\n"
            "• مدة: شهر\n\n"
            "استخدم /start للعودة للقائمة الرئيسية."
        )
    except Exception:
        logger.exception("successful_payment reply failed uid=%s", uid)


__all__ = [
    "handle_pre_checkout",
    "handle_successful_payment",
]
