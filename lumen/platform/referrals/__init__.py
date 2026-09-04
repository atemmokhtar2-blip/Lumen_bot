"""Referral program — config + (later) services/repositories."""
from lumen.platform.referrals.config import (
    REFERRAL_COLLECTION,
    REFERRAL_CREDIT_REASON,
    REFERRAL_QUALIFIED_TARGET,
    REFERRAL_REWARD_CREDITS,
    REFERRAL_REWARD_USD,
    REFERRAL_START_PREFIX,
    REFERRAL_STATS_COLLECTION,
    parse_referrer_from_start_payload,
    referral_deep_link_payload,
)

__all__ = [
    "REFERRAL_COLLECTION",
    "REFERRAL_STATS_COLLECTION",
    "REFERRAL_START_PREFIX",
    "REFERRAL_QUALIFIED_TARGET",
    "REFERRAL_REWARD_USD",
    "REFERRAL_REWARD_CREDITS",
    "REFERRAL_CREDIT_REASON",
    "referral_deep_link_payload",
    "parse_referrer_from_start_payload",
]
