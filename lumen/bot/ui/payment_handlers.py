"""Telegram Stars (XTR) payment handlers — in-Telegram only.

  - pre_checkout_query: must answer within 10s or Telegram cancels the invoice.
  - successful_payment: grant the Pro plan subscription on confirmed payment.

The subscription is persisted to MongoDB (permanent source of truth) AND Redis
(fast-read cache) via subscription_store.write_subscription().  This ensures
the subscription survives Redis flush, TTL expiry, bot deletion, and re-entry.
"""
from __future__ import annotations

import logging
from typing import Any

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

    The subscription is written to:
      1. MongoDB (users.metadata.pro_subscription) — permanent, no TTL
      2. Redis (lumen:tg:session:{uid}.pro_plan) — fast-read cache
      3. context.user_data — in-process for the current request
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

    # Grant the subscription — record in user_data + MongoDB (permanent) + Redis (cache)
    user_data = context.user_data if context.user_data is not None else {}
    pro_record: dict[str, Any] = {}
    try:
        from datetime import datetime, timedelta, timezone
        now = datetime.now(timezone.utc)
        pro_record = {
            "plan_id": PRO_PLAN_ID,
            "started_at": now.isoformat(),
            "expires_at": (now + timedelta(days=30)).isoformat(),
            "stars_paid": amount,
            "charge_id": getattr(sp, "telegram_payment_charge_id", ""),
        }
        user_data["pro_plan"] = dict(pro_record)
    except Exception:
        logger.exception("failed to record pro_plan in user_data uid=%s", uid)

    # ── Persist to MongoDB (permanent source of truth) + Redis (cache) ──
    # This is the CRITICAL write: the subscription must survive Redis flush,
    # TTL expiry, bot deletion, and re-entry.  MongoDB is the permanent DB.
    if pro_record:
        try:
            from lumen.bot.ui.subscription_store import write_subscription
            ok_write = write_subscription(uid, pro_record)
            if not ok_write:
                logger.error("subscription_store write returned False uid=%s", uid)
                try:
                    await msg.reply_text(
                        "تم استلام الدفع، لكن تعذر حفظ الاشتراك الآن. "
                        "تواصل مع الدعم مع رقم العملية وسنفعّله فورًا."
                    )
                except Exception:
                    pass
                return
        except Exception:
            logger.error("subscription_store write FAILED uid=%s", uid, exc_info=True)
            try:
                await msg.reply_text(
                    "تم استلام الدفع، لكن تعذر حفظ الاشتراك الآن. "
                    "تواصل مع الدعم مع رقم العملية وسنفعّله فورًا."
                )
            except Exception:
                pass
            return

    # Also persist the full session to Redis (secondary, best-effort)
    try:
        from lumen.bot.ui.state_store import persist_ui_session
        persist_ui_session(uid, dict(user_data))
    except Exception:
        logger.debug("session persist skipped for pro_plan uid=%s", uid, exc_info=True)

    # Acknowledge to the user
    try:
        await msg.reply_text(
            "\u2705 \u062a\u0645 \u062a\u0641\u0639\u064a\u0644 \u0627\u0634\u062a\u0631\u0627\u0643 Lumen Pro \u0628\u0646\u062c\u0627\u062d!\n\n"
            "\U0001F680 \u0627\u0633\u062a\u0645\u062a\u0639 \u0628\u0640:\n"
            "\u2022 3 GB \u062a\u062e\u0632\u064a\u0646\n"
            "\u2022 2 GB RAM \u0645\u0634\u062a\u0631\u0643\u0629\n"
            "\u2022 0.25 CPU\n"
            "\u2022 \u062d\u062a\u0649 10 \u0628\u0648\u062a\u0627\u062a + \u0627\u0633\u062a\u0636\u0627\u0641\u0629 \u0645\u062c\u0627\u0646\u064a\u0629\n"
            "\u2022 \u0645\u062f\u0629: \u0634\u0647\u0631\n\n"
            "\U0001F4BE \u0627\u0634\u062a\u0631\u0627\u0643\u0643 \u0645\u062d\u0641\u0648\u0638 \u0641\u064a \u0642\u0627\u0639\u062f\u0629 \u0627\u0644\u0628\u064a\u0627\u0646\u0627\u062a \u0628\u0634\u0643\u0644 \u062f\u0627\u0626\u0645.\n"
            "\u064a\u0628\u0642\u0649 \u0627\u0634\u062a\u0631\u0627\u0643\u0643 \u062d\u062a\u0649 \u0644\u0648 \u0645\u0633\u062d\u062a \u0627\u0644\u0628\u0648\u062a \u0648\u062f\u062e\u0644\u062a \u0645\u0631\u0629 \u062b\u0627\u0646\u064a\u0629.\n\n"
            "\u0627\u0633\u062a\u062e\u062f\u0645 /start \u0644\u0644\u0639\u0648\u062f\u0629 \u0644\u0644\u0642\u0627\u0626\u0645\u0629 \u0627\u0644\u0631\u0626\u064a\u0633\u064a\u0629."
        )
    except Exception:
        logger.exception("successful_payment reply failed uid=%s", uid)


__all__ = [
    "handle_pre_checkout",
    "handle_successful_payment",
]
