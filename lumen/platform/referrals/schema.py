"""MongoDB document shapes + index specs for the referral program.

Collection ``referrals`` (one row per referred user — unique):
  {
    referrer_telegram_id: int,   # inviter
    referred_telegram_id: int,   # UNIQUE — one referrer only
    status: "pending"|"qualified"|"rejected",
    created_at: float,
    qualified_at: float|null,
    reward_batch_id: str|null,
    metadata: {}
  }

Collection ``referral_stats`` (one row per referrer):
  {
    referrer_telegram_id: int,  # UNIQUE
    total_invited: int,
    qualified_count: int,
    pending_count: int,
    rejected_count: int,
    reward_paid: bool,
    reward_batch_id: str|null,
    updated_at: float
  }
"""
from __future__ import annotations

from lumen.platform.referrals.config import (
    REFERRAL_COLLECTION,
    REFERRAL_STATS_COLLECTION,
)

# pymongo-style index declarations (applied by MongoReferralRepository.ensure_indexes)
REFERRAL_INDEXES: tuple[dict, ...] = (
    {
        "keys": [("referred_telegram_id", 1)],
        "unique": True,
        "name": "uniq_referred",
    },
    {
        "keys": [("referrer_telegram_id", 1), ("status", 1)],
        "name": "referrer_status",
    },
    {
        "keys": [("referrer_telegram_id", 1), ("qualified_at", 1)],
        "name": "referrer_qualified_at",
    },
)

REFERRAL_STATS_INDEXES: tuple[dict, ...] = (
    {
        "keys": [("referrer_telegram_id", 1)],
        "unique": True,
        "name": "uniq_referrer_stats",
    },
)

__all__ = [
    "REFERRAL_COLLECTION",
    "REFERRAL_STATS_COLLECTION",
    "REFERRAL_INDEXES",
    "REFERRAL_STATS_INDEXES",
]
