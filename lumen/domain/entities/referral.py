"""Referral entity — pure domain (no Mongo / Telegram / credits imports)."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from lumen.domain.value_objects.referral_status import ReferralStatus


@dataclass
class Referral:
    """One directed invite: referrer → referred.

    Counting rule (product):
      Only ``qualified`` referrals count toward the reward target.
      Opening the link alone leaves status ``pending`` and does NOT count.
      Qualification happens when the referred user *uses the bot*.
    """

    referrer_telegram_id: int
    referred_telegram_id: int
    status: ReferralStatus = ReferralStatus.PENDING
    created_at: float = 0.0
    qualified_at: float | None = None
    # Optional correlation when this row contributed to a paid reward batch
    reward_batch_id: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def is_countable(self) -> bool:
        return self.status is ReferralStatus.QUALIFIED

    def public_dict(self) -> dict[str, Any]:
        return {
            "referrer_telegram_id": int(self.referrer_telegram_id),
            "referred_telegram_id": int(self.referred_telegram_id),
            "status": self.status.value,
            "created_at": float(self.created_at or 0.0),
            "qualified_at": self.qualified_at,
            "reward_batch_id": self.reward_batch_id,
        }


@dataclass
class ReferralStats:
    """Aggregate view for one referrer (display + reward gate)."""

    referrer_telegram_id: int
    total_invited: int = 0          # pending + qualified (not rejected)
    qualified_count: int = 0        # used the bot — counts toward target
    pending_count: int = 0          # link only — does not count
    reward_paid: bool = False
    reward_batch_id: str | None = None

    def public_dict(self) -> dict[str, Any]:
        return {
            "referrer_telegram_id": int(self.referrer_telegram_id),
            "total_invited": int(self.total_invited),
            "qualified_count": int(self.qualified_count),
            "pending_count": int(self.pending_count),
            "reward_paid": bool(self.reward_paid),
            "reward_batch_id": self.reward_batch_id,
        }
