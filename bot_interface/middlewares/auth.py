"""Authentication and process-safe rate limiting middleware helpers."""
from __future__ import annotations

from ..config import RATE_LIMIT_PER_MINUTE, RATE_LIMIT_WINDOW_SECONDS


def rate_limit_ok(user_id: int) -> bool:
    try:
        from b2b_platform.rate_limit import get_rate_limiter
        return get_rate_limiter().allow(
            f"tg:{int(user_id)}",
            limit=RATE_LIMIT_PER_MINUTE,
            window_sec=RATE_LIMIT_WINDOW_SECONDS,
        )
    except Exception:
        return True


def rate_limit_wait_seconds(user_id: int) -> int:
    try:
        from b2b_platform.rate_limit import get_rate_limiter
        return get_rate_limiter().seconds_until_allow(
            f"tg:{int(user_id)}",
            limit=RATE_LIMIT_PER_MINUTE,
            window_sec=RATE_LIMIT_WINDOW_SECONDS,
        )
    except Exception:
        return int(RATE_LIMIT_WINDOW_SECONDS)
