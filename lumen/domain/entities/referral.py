"""Referral aggregate — invariants enforced in factory / transitions."""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

from lumen.domain.value_objects.referral_status import ReferralStatus


class ReferralError(ValueError):
    """Domain rule violation for referrals."""


@dataclass
class Referral:
    """referrer invited referred.

    Product rule (hard):
      - Link open → pending → does NOT count.
      - Referred user uses the bot → qualified → counts.
      - Reward at 50 *qualified* (not 50 link clicks).
    """

    referrer_telegram_id: int
    referred_telegram_id: int
    status: ReferralStatus = ReferralStatus.PENDING
    created_at: float = 0.0
    qualified_at: float | None = None
    reward_batch_id: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.referrer_telegram_id = int(self.referrer_telegram_id)
        self.referred_telegram_id = int(self.referred_telegram_id)
        if isinstance(self.status, str):
            self.status = ReferralStatus(self.status)

    def is_countable(self) -> bool:
        return self.status.counts_toward_reward()

    def qualify(self, *, at: float | None = None) -> None:
        """Transition pending → qualified (bot use). Idempotent if already qualified."""
        if self.status is ReferralStatus.REJECTED:
            raise ReferralError("cannot_qualify_rejected_referral")
        if self.status is ReferralStatus.QUALIFIED:
            return
        self.status = ReferralStatus.QUALIFIED
        self.qualified_at = float(at if at is not None else time.time())

    def reject(self, reason: str = "") -> None:
        if self.status is ReferralStatus.QUALIFIED:
            raise ReferralError("cannot_reject_qualified_referral")
        self.status = ReferralStatus.REJECTED
        if reason:
            self.metadata["reject_reason"] = str(reason)[:120]

    def public_dict(self) -> dict[str, Any]:
        return {
            "referrer_telegram_id": self.referrer_telegram_id,
            "referred_telegram_id": self.referred_telegram_id,
            "status": self.status.value,
            "counts_toward_reward": self.is_countable(),
            "created_at": float(self.created_at or 0.0),
            "qualified_at": self.qualified_at,
            "reward_batch_id": self.reward_batch_id,
        }

    @staticmethod
    def create_pending(referrer_telegram_id: int, referred_telegram_id: int) -> "Referral":
        """Factory — enforces identity rules before persistence."""
        a = int(referrer_telegram_id)
        b = int(referred_telegram_id)
        if a <= 0 or b <= 0:
            raise ReferralError("invalid_telegram_id")
        if a == b:
            raise ReferralError("self_referral_forbidden")
        return Referral(
            referrer_telegram_id=a,
            referred_telegram_id=b,
            status=ReferralStatus.PENDING,
            created_at=time.time(),
        )


@dataclass
class ReferralStats:
    referrer_telegram_id: int
    total_invited: int = 0
    qualified_count: int = 0
    pending_count: int = 0
    rejected_count: int = 0
    reward_paid: bool = False
    reward_batch_id: str | None = None

    def remaining_to_reward(self, target: int) -> int:
        t = max(0, int(target))
        return max(0, t - int(self.qualified_count))

    def reward_unlocked(self, target: int) -> bool:
        return int(self.qualified_count) >= max(1, int(target)) and not self.reward_paid

    def public_dict(self) -> dict[str, Any]:
        return {
            "referrer_telegram_id": int(self.referrer_telegram_id),
            "total_invited": int(self.total_invited),
            "qualified_count": int(self.qualified_count),
            "pending_count": int(self.pending_count),
            "rejected_count": int(self.rejected_count),
            "reward_paid": bool(self.reward_paid),
            "reward_batch_id": self.reward_batch_id,
        }
