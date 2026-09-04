"""Referral use-cases — register, qualify on bot use, atomic one-time reward."""
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
_register_hits: dict[int, list[float]] = {}
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


def handle_register_referral(cmd: RegisterReferralCommand) -> RegisterReferralResult:
    from lumen.platform.referrals import get_referral_repository

    referrer = int(cmd.referrer_telegram_id)
    referred = int(cmd.referred_telegram_id)
    if referrer <= 0 or referred <= 0:
        return RegisterReferralResult(ok=False, error="invalid_telegram_id")
    if referrer == referred:
        return RegisterReferralResult(ok=False, error="self_referral_forbidden")


    # Soft rate-limit: max N successful register attempts per referrer per minute
    try:
        from lumen.platform.referrals.config import REFERRAL_REGISTER_RATE_PER_MIN
        import time as _time
        now = _time.time()
        window = 60.0
        hits = [t for t in _register_hits.get(referrer, []) if now - t < window]
        if len(hits) >= int(REFERRAL_REGISTER_RATE_PER_MIN):
            return RegisterReferralResult(ok=False, error="register_rate_limited")
        hits.append(now)
        _register_hits[referrer] = hits
    except Exception:
        pass


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
        return RegisterReferralResult(ok=False, error=str(exc) or type(exc).__name__)
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
        notify_text = ""
        reward_granted = False

        if newly_qualified:
            notify_text = (
                "صديقك بدأ يستخدم Lumen."
                + chr(10)
                + "التقدم: %s/%s " % (stats.qualified_count, REFERRAL_QUALIFIED_TARGET)
                + "(يُحتسب من يستخدم البوت فقط)."
            )

        if is_reward_due(stats, target=REFERRAL_QUALIFIED_TARGET):
            batch = "referral-reward-%s-%s" % (
                ref.referrer_telegram_id,
                REFERRAL_QUALIFIED_TARGET,
            )
            claimed = repo.claim_reward_slot(
                ref.referrer_telegram_id,
                batch_id=batch,
                min_qualified=int(REFERRAL_QUALIFIED_TARGET),
            )
            if claimed:
                reward_granted = _grant_referral_reward(ref.referrer_telegram_id)
                if reward_granted:
                    stats = repo.stats_for(ref.referrer_telegram_id)
                    notify_text = (
                        "مبروك! وصلت لـ %s مستخدم استخدموا البوت." % REFERRAL_QUALIFIED_TARGET
                        + chr(10)
                        + "تم إضافة مكافأة $%s (%s رصيد) لحسابك."
                        % (REFERRAL_REWARD_USD, _reward_credit_amount())
                    )
                else:
                    repo.release_reward_slot(ref.referrer_telegram_id)
                    logger.error(
                        "referral reward credit failed after claim referrer_tg=%s",
                        ref.referrer_telegram_id,
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
    except Exception as exc:
        logger.warning("qualify_referral failed: %s", type(exc).__name__)
        return QualifyReferralResult(ok=False, error=type(exc).__name__)


def _reward_credit_amount() -> int:
    configured = int(REFERRAL_REWARD_CREDITS or 0)
    if configured > 0:
        return configured
    return max(1, int(REFERRAL_REWARD_USD) * 100)


def _grant_referral_reward(referrer_telegram_id: int) -> bool:
    amount = _reward_credit_amount()
    tid = "tg:%s" % int(referrer_telegram_id)
    key = "referral-reward-%s-%s" % (
        int(referrer_telegram_id),
        REFERRAL_QUALIFIED_TARGET,
    )
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
