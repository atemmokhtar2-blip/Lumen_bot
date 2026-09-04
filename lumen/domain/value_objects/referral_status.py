"""Referral lifecycle status — domain only (no I/O)."""
from __future__ import annotations

from enum import Enum


class ReferralStatus(str, Enum):
    """How far a referred user has progressed.

    pending   — deep-link accepted; user has NOT yet used the bot (does not count).
    qualified — referred user used the bot (counts toward the 50 target).
    rejected  — invalid (self-referral, duplicate, policy) — never counts.
    """

    PENDING = "pending"
    QUALIFIED = "qualified"
    REJECTED = "rejected"
