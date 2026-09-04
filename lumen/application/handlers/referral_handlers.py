"""Referral use-cases — register link-open; qualify on bot use; one-time reward."""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Optional

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

    try:
        repo = get_referral_repository()
        existing = repo.get_by_referred(int(cmd.referred_telegram_id))
        if existing is not None:
            return RegisterReferralResult(
                ok=True,
                referral=existing,
                already_registered=True,
            )
        ref = repo.create_pending(
            int(cmd.referrer_telegram_id), int(cmd.referred_telegram_id)
        )
        return RegisterReferralResult(ok=True, referral=ref)
    except ReferralError as exc:
        return RegisterReferralResult(ok=False, error=str(exc) or type(exc).__name__)
    except Exception as exc:
        logger.warning("register_referral failed: %s", type(exc).__name__)
        return RegisterReferralResult(ok=False, error=type(exc).__name__)


def handle_qualify_referral(cmd: QualifyReferralCommand) -> QualifyReferralResult:
    """Qualify only when event proves bot use; grant $5 credits at target once."""
    from lumen.platform.referrals import get_referral_repository

    if not should_count_as_bot_use(cmd.event):
        return QualifyReferralResult(ok=False, error="event_not_bot_use")

    try:
        repo = get_referral_repository()
        ref = repo.mark_qualified(int(cmd.referred_telegram_id))
        if ref is None:
            return QualifyReferralResult(ok=True, error="no_referral")  # not invited — fine
        stats = repo.stats_for(ref.referrer_telegram_id)
        reward_granted = False
        if is_reward_due(stats, target=REFERRAL_QUALIFIED_TARGET):
            reward_granted = _grant_referral_reward(ref.referrer_telegram_id, stats)
            if reward_granted:
                batch = f"referral-reward-{ref.referrer_telegram_id}-{REFERRAL_QUALIFIED_TARGET}"
                stats = repo.mark_reward_paid(ref.referrer_telegram_id, batch_id=batch)
        return QualifyReferralResult(
            ok=True, referral=ref, stats=stats, reward_granted=reward_granted
        )
    except ReferralError as exc:
        return QualifyReferralResult(ok=False, error=str(exc) or type(exc).__name__)
    except Exception as exc:
        logger.warning("qualify_referral failed: %s", type(exc).__name__)
        return QualifyReferralResult(ok=False, error=type(exc).__name__)


def _grant_referral_reward(referrer_telegram_id: int, stats: ReferralStats) -> bool:
    """Credit referrer once via CreditService (reason=referral_bonus)."""
    amount = int(REFERRAL_REWARD_CREDITS or 0)
    if amount <= 0:
        # Fallback: treat $1 ≈ 100 credits if pricing not configured
        amount = max(1, int(REFERRAL_REWARD_USD) * 100)
    try:
        from lumen.platform.credits import get_credit_service
        from lumen.platform.credits.llm_live import tenant_id_from_user

        tid = tenant_id_from_user(int(referrer_telegram_id))
        if not tid:
            tid = f"tg:{int(referrer_telegram_id)}"
        key = f"referral-reward-{int(referrer_telegram_id)}-{REFERRAL_QUALIFIED_TARGET}"
        svc = get_credit_service()
        result = svc.credit_credits(
            str(tid),
            amount,
            reason=REFERRAL_CREDIT_REASON,
            reference_id=key,
            idempotency_key=key,
            expires_at=None,
        )
        ok = bool(getattr(result, "ok", False))
        if ok:
            logger.info(
                "referral reward granted referrer_tg=%s amount=%s target=%s",
                referrer_telegram_id,
                amount,
                REFERRAL_QUALIFIED_TARGET,
            )
        else:
            logger.warning(
                "referral reward credit failed referrer_tg=%s reason=%s",
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
