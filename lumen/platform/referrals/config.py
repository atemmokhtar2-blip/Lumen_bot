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
REFERRAL_REWARD_CREDITS = _int_env("REFERRAL_REWARD_CREDITS", 500)
REFERRAL_MILESTONE_STEP = _int_env("REFERRAL_MILESTONE_STEP", 10)
REFERRAL_MILESTONE_CREDITS = _int_env("REFERRAL_MILESTONE_CREDITS", 100)
REFERRAL_NOTIFY_EVERY = _int_env("REFERRAL_NOTIFY_EVERY", 5)
REFERRAL_CREDIT_REASON = "referral_bonus"
REFERRAL_COLLECTION = "referrals"
REFERRAL_STATS_COLLECTION = "referral_stats"

# Anti-abuse (phase 3)
REFERRAL_MAX_PER_REFERRER = _int_env("REFERRAL_MAX_PER_REFERRER", 100)
REFERRAL_REGISTER_RATE_PER_MIN = _int_env("REFERRAL_REGISTER_RATE_PER_MIN", 20)

def referral_admin_ids() -> set[int]:
    """Telegram user ids allowed to run /referral_stats."""
    raw = (os.getenv("REFERRAL_ADMIN_IDS") or os.getenv("ALLOWED_USER_IDS") or "").strip()
    out: set[int] = set()
    for part in raw.split(","):
        part = part.strip()
        if part.isdigit():
            out.add(int(part))
    return out

def is_referral_admin(telegram_user_id: int) -> bool:
    admins = referral_admin_ids()
    if not admins:
        return False
    try:
        return int(telegram_user_id) in admins
    except (TypeError, ValueError):
        return False


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


def is_referral_dev_environment() -> bool:
    """True only for explicit local/test — never treat unset ENVIRONMENT as dev.

    Platform markers (K8s, Railway, Render, Fly, Heroku) force non-dev even if
    someone sets ENVIRONMENT=dev by mistake.
    """
    import os
    for marker in (
        "KUBERNETES_SERVICE_HOST",
        "RAILWAY_ENVIRONMENT",
        "RAILWAY_SERVICE_NAME",
        "RENDER",
        "RENDER_SERVICE_ID",
        "FLY_APP_NAME",
        "DYNO",
    ):
        if (os.getenv(marker) or "").strip():
            return False
    env = (os.getenv("ENVIRONMENT") or os.getenv("ENV") or "").strip().lower()
    return env in {"dev", "development", "local", "test"}


def referral_milestones() -> list[int]:
    step = max(1, int(REFERRAL_MILESTONE_STEP))
    target = max(step, int(REFERRAL_QUALIFIED_TARGET))
    return list(range(step, target + 1, step))
