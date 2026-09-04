"""Referral product rules — single source of truth.

Hard product rule:
  Reward requires REFERRAL_QUALIFIED_TARGET users who **used the bot**.
  Opening the referral link alone never counts.
"""
from __future__ import annotations

import os


def _int_env(name: str, default: int) -> int:
    raw = (os.getenv(name) or "").strip()
    if not raw:
        return default
    try:
        return max(0, int(raw))
    except ValueError:
        return default


REFERRAL_START_PREFIX = "ref_"
REFERRAL_QUALIFIED_TARGET = _int_env("REFERRAL_QUALIFIED_TARGET", 50)
REFERRAL_REWARD_USD = _int_env("REFERRAL_REWARD_USD", 5)
REFERRAL_REWARD_CREDITS = _int_env("REFERRAL_REWARD_CREDITS", 0)
REFERRAL_CREDIT_REASON = "referral_bonus"
REFERRAL_COLLECTION = "referrals"
REFERRAL_STATS_COLLECTION = "referral_stats"


def referral_deep_link_payload(telegram_user_id: int) -> str:
    uid = int(telegram_user_id)
    if uid <= 0:
        raise ValueError("invalid_telegram_id")
    return f"{REFERRAL_START_PREFIX}{uid}"


def parse_referrer_from_start_payload(payload: str) -> int | None:
    raw = (payload or "").strip()
    if not raw.startswith(REFERRAL_START_PREFIX):
        return None
    tail = raw[len(REFERRAL_START_PREFIX) :].strip()
    if not tail.isdigit():
        return None
    uid = int(tail)
    return uid if uid > 0 else None


def bot_username_link(bot_username: str, telegram_user_id: int) -> str:
    """https://t.me/<bot>?start=ref_<id>"""
    user = (bot_username or "").strip().lstrip("@")
    if not user:
        raise ValueError("bot_username_required")
    return f"https://t.me/{user}?start={referral_deep_link_payload(telegram_user_id)}"
