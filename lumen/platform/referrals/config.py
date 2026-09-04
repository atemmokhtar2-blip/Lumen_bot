"""Referral product rules — single source of truth.

Reward model (confirmed):
  - Invitee must **use the bot** to count (not merely open the referral link).
  - After **50 qualified** invitees, referrer receives a **$5** credit grant once.
"""
from __future__ import annotations

import os


def _int_env(name: str, default: int) -> int:
    raw = (os.getenv(name) or "").strip()
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


# Deep-link payload: /start ref_<telegram_id>
REFERRAL_START_PREFIX = "ref_"

# How many invitees must *use the bot* before reward
REFERRAL_QUALIFIED_TARGET = _int_env("REFERRAL_QUALIFIED_TARGET", 50)

# USD face value of the one-time reward (mapped to credits in a later phase)
REFERRAL_REWARD_USD = _int_env("REFERRAL_REWARD_USD", 5)

# Credits granted for that USD (override when pricing is fixed)
# 0 means "resolve from pricing table at grant time" in a later phase
REFERRAL_REWARD_CREDITS = _int_env("REFERRAL_REWARD_CREDITS", 0)

# CreditService reason (already allow-listed as promotional in credits service)
REFERRAL_CREDIT_REASON = "referral_bonus"

# Mongo collection name (implementation phase)
REFERRAL_COLLECTION = "referrals"
REFERRAL_STATS_COLLECTION = "referral_stats"


def referral_deep_link_payload(telegram_user_id: int) -> str:
    return f"{REFERRAL_START_PREFIX}{int(telegram_user_id)}"


def parse_referrer_from_start_payload(payload: str) -> int | None:
    """Return referrer telegram id from /start payload, or None if not a referral link."""
    raw = (payload or "").strip()
    if not raw.startswith(REFERRAL_START_PREFIX):
        return None
    tail = raw[len(REFERRAL_START_PREFIX) :].strip()
    if not tail.isdigit():
        return None
    uid = int(tail)
    return uid if uid > 0 else None
