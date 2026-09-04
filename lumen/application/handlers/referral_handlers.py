"""Referral use-cases — register, qualify on bot use, atomic one-time reward."""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Optional

from lumen.application.commands.qualify_referral import QualifyReferralCommand
from lumen.application.commands.register_referral import RegisterReferralCommand
from lumen.domain.entities.referral import Referral, ReferralError, ReferralStats
from lumen.domain.services.referral_policy import should_count_as_bot_use
from lumen.platform.referrals.config import (
    REFERRAL_CREDIT_REASON,
    REFERRAL_MILESTONE_CREDITS,
    REFERRAL_NOTIFY_EVERY,
    REFERRAL_QUALIFIED_TARGET,
    REFERRAL_REGISTER_RATE_PER_MIN,
    REFERRAL_REWARD_CREDITS,
    REFERRAL_REWARD_USD,
    referral_milestones,
)

logger = logging.getLogger(__name__)
_REFERRAL_PROMO_TTL_SEC = 365 * 24 * 3600


@dataclass
class RegisterReferralResult:
    ok: bool
    referral: Optional[Referral] = None
    error: str = ""
    already_registered: bool = False


@dataclass
class QualifyReferralResult:
    ok: bool
    referral: Optional[Referral] = None
    stats: Optional[ReferralStats] = None
    reward_granted: bool = False
    error: str = ""
    notify_referrer_id: int = 0
    notify_text: str = ""


def _rate_allow(key: str, *, limit: int) -> bool:
    if limit <= 0:
        return True
    try:
        from lumen.platform.rate_limit import get_rate_limiter
        return bool(get_rate_limiter().allow(key, limit=limit, window_sec=60.0))
    except Exception:
        logger.debug("referral rate-limit backend unavailable", exc_info=True)
        return True


def handle_register_referral(cmd: RegisterReferralCommand) -> RegisterReferralResult:
    from lumen.platform.referrals import get_referral_repository

    referrer = int(cmd.referrer_telegram_id)
    referred = int(cmd.referred_telegram_id)
    if referrer <= 0 or referred <= 0:
        return RegisterReferralResult(ok=False, error="invalid_telegram_id")
    if referrer == referred:
        return RegisterReferralResult(ok=False, error="self_referral_forbidden")

    try:
        repo = get_referral_repository()
        # Idempotent FIRST — never burn rate limit on repeat /start
        existing = repo.get_by_referred(referred)
        if existing is not None:
            return RegisterReferralResult(
                ok=True, referral=existing, already_registered=True
            )

        lim = int(REFERRAL_REGISTER_RATE_PER_MIN)
        if not _rate_allow("referral_register:referrer:%s" % referrer, limit=lim):
            return RegisterReferralResult(ok=False, error="register_rate_limited")
        if not _rate_allow(
            "referral_register:referred:%s" % referred,
            limit=max(3, lim // 4),
        ):
            return RegisterReferralResult(ok=False, error="register_rate_limited")

        ref = repo.create_pending(referrer, referred)
        logger.info("referral registered referrer_tg=%s referred_tg=%s", referrer, referred)
        return RegisterReferralResult(ok=True, referral=ref)
    except ReferralError as exc:
        return RegisterReferralResult(ok=False, error=str(exc) or type(exc).__name__)
    except RuntimeError as exc:
        logger.error("register_referral backend: %s", exc)
        msg = str(exc) or ""
        if "mongo_init_failed" in msg or "Mongo URI missing" in msg or "MONGODB" in msg:
            return RegisterReferralResult(ok=False, error="referral_backend_unavailable")
        return RegisterReferralResult(ok=False, error="referral_backend_unavailable")
    except Exception as exc:
        logger.warning("register_referral failed: %s", type(exc).__name__)
        return RegisterReferralResult(ok=False, error=type(exc).__name__)


def handle_qualify_referral(cmd: QualifyReferralCommand) -> QualifyReferralResult:
    from lumen.platform.referrals import get_referral_repository

    if not should_count_as_bot_use(cmd.event):
        return QualifyReferralResult(ok=False, error="event_not_bot_use")

    referred = int(cmd.referred_telegram_id)
    if referred <= 0:
        return QualifyReferralResult(ok=False, error="invalid_telegram_id")

    try:
        repo = get_referral_repository()
        existing = repo.get_by_referred(referred)
        if existing is None:
            return QualifyReferralResult(ok=True, error="no_referral")

        newly_qualified = existing.status.value != "qualified"
        ref = repo.mark_qualified(referred) if newly_qualified else existing
        if ref is None:
            return QualifyReferralResult(ok=True, error="no_referral")

        stats = repo.stats_for(ref.referrer_telegram_id)
        live_qualified = int(repo.count_qualified(ref.referrer_telegram_id))
        stats.qualified_count = live_qualified
        notify_text = ""
        reward_granted = False

        if newly_qualified:
            notify_text = (
                "صديقك بدأ يستخدم Lumen."
                + chr(10)
                + "التقدم: %s/%s " % (live_qualified, REFERRAL_QUALIFIED_TARGET)
                + "(يُحتسب من يستخدم البوت فقط)."
            )

        # Progressive milestones every N qualified (default 10 → $1 each up to target)
        for ms in referral_milestones():
            if live_qualified < int(ms):
                break
            batch = "referral-ms-%s-%s" % (ref.referrer_telegram_id, ms)
            try:
                claimed = repo.claim_milestone_slot(
                    ref.referrer_telegram_id, milestone=int(ms), batch_id=batch
                )
            except Exception:
                claimed = False
            if not claimed:
                continue
            amount = int(REFERRAL_MILESTONE_CREDITS or 0) or max(
                1, int(REFERRAL_REWARD_CREDITS or 500) // max(1, len(referral_milestones()))
            )
            ok = _grant_referral_reward_amount(
                ref.referrer_telegram_id, amount=amount, batch_key=batch
            )
            if ok:
                reward_granted = True
                notify_text = (
                    "مبروك! وصلت لـ %s مستخدم استخدموا البوت." % ms
                    + chr(10)
                    + "تم إضافة %s رصيد (حافز إحالة)." % amount
                )
            else:
                logger.error(
                    "milestone reward failed referrer_tg=%s ms=%s",
                    ref.referrer_telegram_id,
                    ms,
                )

        # Nudge every REFERRAL_NOTIFY_EVERY newly counted (no payout)
        if newly_qualified and not reward_granted and int(REFERRAL_NOTIFY_EVERY) > 0:
            if live_qualified > 0 and live_qualified % int(REFERRAL_NOTIFY_EVERY) == 0:
                nxt = None
                for ms in referral_milestones():
                    if live_qualified < int(ms):
                        nxt = int(ms)
                        break
                if nxt is not None:
                    notify_text = (
                        "تقدم الإحالات: %s/%s نشط." % (live_qualified, REFERRAL_QUALIFIED_TARGET)
                        + chr(10)
                        + "باقي %s للمكافأة التالية." % max(0, nxt - live_qualified)
                    )
                else:
                    notify_text = (
                        "تقدم الإحالات: %s/%s نشط." % (live_qualified, REFERRAL_QUALIFIED_TARGET)
                    )


        return QualifyReferralResult(
            ok=True,
            referral=ref,
            stats=stats,
            reward_granted=reward_granted,
            notify_referrer_id=int(ref.referrer_telegram_id) if notify_text else 0,
            notify_text=notify_text,
        )
    except ReferralError as exc:
        return QualifyReferralResult(ok=False, error=str(exc) or type(exc).__name__)
    except RuntimeError as exc:
        logger.error("qualify_referral backend: %s", exc)
        return QualifyReferralResult(ok=False, error="referral_backend_unavailable")
    except Exception as exc:
        logger.warning("qualify_referral failed: %s", type(exc).__name__)
        return QualifyReferralResult(ok=False, error=type(exc).__name__)


def _reward_credit_amount() -> int:
    configured = int(REFERRAL_REWARD_CREDITS or 0)
    if configured > 0:
        return configured
    return max(1, int(REFERRAL_REWARD_USD) * 100)


def _grant_referral_reward_amount(
    referrer_telegram_id: int, *, amount: int, batch_key: str
) -> bool:
    amount = int(amount)
    if amount <= 0:
        return False
    tid = "tg:%s" % int(referrer_telegram_id)
    key = str(batch_key)
    expires = time.time() + _REFERRAL_PROMO_TTL_SEC
    try:
        import os
        from lumen.platform.credits import get_credit_service
        from lumen.platform.referrals.config import is_referral_dev_environment

        svc = get_credit_service()
        store_name = type(getattr(svc, "_store", None)).__name__
        if store_name == "MemoryCreditsStore" and not is_referral_dev_environment():
            logger.error("referral reward refused: MemoryCreditsStore in non-dev")
            return False
        result = svc.credit_credits(
            tid,
            amount,
            reason=REFERRAL_CREDIT_REASON,
            reference_id=key,
            idempotency_key=key,
            promotional=True,
            promo_expires_at=expires,
            metadata={
                "usd_hint": round(amount / 100.0, 2),
                "batch": key,
                "kind": "referral_milestone",
            },
        )
        ok = bool(getattr(result, "ok", False))
        if ok:
            logger.info(
                "referral milestone granted referrer_tg=%s amount=%s key=%s",
                referrer_telegram_id,
                amount,
                key,
            )
        else:
            logger.warning(
                "referral milestone denied referrer_tg=%s reason=%s",
                referrer_telegram_id,
                getattr(result, "reason", ""),
            )
        return ok
    except Exception as exc:
        logger.warning(
            "referral milestone exception referrer_tg=%s: %s",
            referrer_telegram_id,
            type(exc).__name__,
        )
        return False


def _grant_referral_reward(referrer_telegram_id: int) -> bool:

    amount = _reward_credit_amount()
    tid = "tg:%s" % int(referrer_telegram_id)
    key = "referral-reward-%s-%s" % (
        int(referrer_telegram_id),
        REFERRAL_QUALIFIED_TARGET,
    )
    expires = time.time() + _REFERRAL_PROMO_TTL_SEC
    try:
        import os
        from lumen.platform.credits import get_credit_service

        svc = get_credit_service()
        store_name = type(getattr(svc, "_store", None)).__name__
        from lumen.platform.referrals.config import is_referral_dev_environment
        # Fail closed: memory credits are not real in deployed environments
        if store_name == "MemoryCreditsStore" and not is_referral_dev_environment():
            logger.error(
                "referral reward refused: MemoryCreditsStore without durable DB "
                "(set DATABASE_URL/POSTGRES_URL; unset platform env markers for local dev)"
            )
            return False

        result = svc.credit_credits(
            tid,
            amount,
            reason=REFERRAL_CREDIT_REASON,
            reference_id=key,
            idempotency_key=key,
            promotional=True,
            promo_expires_at=expires,
            metadata={
                "usd": int(REFERRAL_REWARD_USD),
                "target": int(REFERRAL_QUALIFIED_TARGET),
                "kind": "referral_reward",
            },
        )
        ok = bool(getattr(result, "ok", False))
        if ok:
            logger.info(
                "referral reward granted referrer_tg=%s amount=%s",
                referrer_telegram_id,
                amount,
            )
        else:
            logger.warning(
                "referral reward denied referrer_tg=%s reason=%s",
                referrer_telegram_id,
                getattr(result, "reason", ""),
            )
        return ok
    except Exception as exc:
        logger.warning(
            "referral reward exception referrer_tg=%s: %s",
            referrer_telegram_id,
            type(exc).__name__,
        )
        return False
