"""Referral program."""
from lumen.platform.referrals.config import (
    REFERRAL_COLLECTION,
    REFERRAL_CREDIT_REASON,
    REFERRAL_MAX_PER_REFERRER,
    REFERRAL_QUALIFIED_TARGET,
    REFERRAL_REGISTER_RATE_PER_MIN,
    REFERRAL_REWARD_CREDITS,
    REFERRAL_REWARD_USD,
    REFERRAL_START_PREFIX,
    REFERRAL_STATS_COLLECTION,
    bot_username_link,
    parse_referrer_from_start_payload,
    referral_deep_link_payload,
)
from lumen.platform.referrals.mongo_repository import (
    MemoryReferralRepository,
    MongoReferralRepository,
    get_referral_repository,
    reset_referral_repository_for_tests,
)

__all__ = [
    "REFERRAL_COLLECTION",
    "REFERRAL_STATS_COLLECTION",
    "REFERRAL_START_PREFIX",
    "REFERRAL_QUALIFIED_TARGET",
    "REFERRAL_REWARD_USD",
    "REFERRAL_REWARD_CREDITS",
    "REFERRAL_CREDIT_REASON",
    "REFERRAL_MAX_PER_REFERRER",
    "REFERRAL_REGISTER_RATE_PER_MIN",
    "referral_deep_link_payload",
    "parse_referrer_from_start_payload",
    "bot_username_link",
    "MongoReferralRepository",
    "MemoryReferralRepository",
    "get_referral_repository",
    "reset_referral_repository_for_tests",
]
