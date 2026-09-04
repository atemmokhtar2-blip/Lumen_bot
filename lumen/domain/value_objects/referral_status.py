"""Referral lifecycle — only QUALIFIED counts toward the reward target."""
from __future__ import annotations

from enum import Enum


class ReferralStatus(str, Enum):
    """pending = link only (no credit toward 50).

    qualified = referred user used the bot (counts).
    rejected = invalid invite (self/duplicate/policy).
    """

    PENDING = "pending"
    QUALIFIED = "qualified"
    REJECTED = "rejected"

    def counts_toward_reward(self) -> bool:
        return self is ReferralStatus.QUALIFIED
