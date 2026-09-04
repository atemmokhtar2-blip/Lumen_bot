"""Referral qualification & reward gates — pure functions, no I/O."""
from __future__ import annotations

from lumen.domain.entities.referral import ReferralStats


# Events that mean the referred user *used the bot* (not link-open alone).
# Link-open /start with only ref_ payload must NOT pass this check by itself
# unless paired with a real bot action in a later phase wire-up.
BOT_USE_EVENTS = frozenset(
    {
        "message",           # user sent a normal message
        "generation_success",  # finished a generation job
        "command_non_start", # any command other than bare /start
    }
)


def should_count_as_bot_use(event: str) -> bool:
    """True only for actions that prove bot usage (counts toward 50)."""
    return (event or "").strip().lower() in BOT_USE_EVENTS


def is_reward_due(stats: ReferralStats, *, target: int) -> bool:
    """One-time reward when qualified_count reaches target and not yet paid."""
    return stats.reward_unlocked(target)


def is_existing_user_ineligible_for_referral(*, already_known: bool) -> bool:
    """Strict product rule: only first-time users count for the referrer.

    already_known=True means the telegram id was seen in the platform before
    this referral deep-link (users table / tenant store / prior activity).
    """
    return bool(already_known)
