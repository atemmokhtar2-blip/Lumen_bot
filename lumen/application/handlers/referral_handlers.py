"""Referral use-cases — register link-open; qualify on bot use; one-time reward."""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Optional

from lumen.application.commands.qualify_referral import QualifyReferralCommand
from lumen.application.commands.register_referral import RegisterReferralCommand
from lumen.domain.entities.referral import Referral, ReferralError, ReferralStats
from lumen.domain.services.referral_policy import is_reward_due, should_count_as_bot_use
from lumen.platform.referrals.config import (
    REFERRAL_CREDIT_REASON,
    REFERRAL_QUALIFIED_TARGET,
    REFERRAL_REWARD_CREDITS,
    REFERRAL_REWARD_USD,
)

logger = logging.getLogger(__name__)

# Promotional referral credits must expire (CreditService fail-closed rule)
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
        existing = repo.get_by_referred(referred)
        if existing is not None:
            return RegisterReferralResult(
                ok=True, referral=existing, already_registered=True
            )
        ref = repo.create_pending(referrer, referred)
        return RegisterReferralResult(ok=True, referral=ref)
    except ReferralError as exc:
        msg = str(exc) or type(exc).__name__
        if "already" in msg:
            return RegisterReferralResult(ok=False, error="referred_already_registered")
        return RegisterReferralResult(ok=False, error=msg)
    except Exception as exc:
        logger.warning("register_referral failed: %s", type(exc).__name__)
        return RegisterReferralResult(ok=False, error=type(exc).__name__)


def handle_qualify_referral(cmd: QualifyReferralCommand) -> QualifyReferralResult:
    """Qualify only when event proves bot use; grant promotional credits at target."""
    from lumen.platform.referrals import get_referral_repository

    if not should_count_as_bot_use(cmd.event):
        return QualifyReferralResult(ok=False, error="event_not_bot_use")

    referred = int(cmd.referred_telegram_id)
    if referred <= 0:
        return QualifyReferralResult(ok=False, error="invalid_telegram_id")

    try:
        repo = get_referral_repository()
        # Fast path: not an invitee — avoid mark_qualified work
        existing = repo.get_by_referred(referred)
        if existing is None:
            return QualifyReferralResult(ok=True, error="no_referral")
        if existing.status.value == "qualified":
            stats = repo.stats_for(existing.referrer_telegram_id)
            return QualifyReferralResult(ok=True, referral=existing, stats=stats)

        ref = repo.mark_qualified(referred)
        if ref is None:
            return QualifyReferralResult(ok=True, error="no_referral")

        stats = repo.stats_for(ref.referrer_telegram_id)
        reward_granted = False
        if is_reward_due(stats, target=REFERRAL_QUALIFIED_TARGET):
            reward_granted = _grant_referral_reward(ref.referrer_telegram_id)
            if reward_granted:
                batch = (
                    f"referral-reward-{ref.referrer_telegram_id}-"
                    f"{REFERRAL_QUALIFIED_TARGET}"
                )
                stats = repo.mark_reward_paid(
                    ref.referrer_telegram_id, batch_id=batch
                )
            else:
                logger.error(
                    "referral reward credit FAILED referrer_tg=%s qualified=%s",
                    ref.referrer_telegram_id,
                    stats.qualified_count,
                )
        return QualifyReferralResult(
            ok=True, referral=ref, stats=stats, reward_granted=reward_granted
        )
    except ReferralError as exc:
        return QualifyReferralResult(ok=False, error=str(exc) or type(exc).__name__)
    except Exception as exc:
        logger.warning("qualify_referral failed: %s", type(exc).__name__)
        return QualifyReferralResult(ok=False, error=type(exc).__name__)


def _reward_credit_amount() -> int:
    """Credits to grant. Prefer REFERRAL_REWARD_CREDITS; else USD * 100."""
    configured = int(REFERRAL_REWARD_CREDITS or 0)
    if configured > 0:
        return configured
    return max(1, int(REFERRAL_REWARD_USD) * 100)


def _grant_referral_reward(referrer_telegram_id: int) -> bool:
    """Credit referrer once. Must satisfy CreditService promo rules."""
    amount = _reward_credit_amount()
    tid = f"tg:{int(referrer_telegram_id)}"
    key = f"referral-reward-{int(referrer_telegram_id)}-{REFERRAL_QUALIFIED_TARGET}"
    expires = time.time() + _REFERRAL_PROMO_TTL_SEC
    try:
        from lumen.platform.credits import get_credit_service

        result = get_credit_service().credit_credits(
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
                "referral reward granted referrer_tg=%s amount=%s expires_in_days=365",
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
