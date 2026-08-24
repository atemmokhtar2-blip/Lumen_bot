"""Authentication and process-safe rate limiting middleware helpers."""
from __future__ import annotations

from ..config import RATE_LIMIT_PER_MINUTE, RATE_LIMIT_WINDOW_SECONDS


def rate_limit_ok(user_id: int) -> bool:
    try:
        from b2b_platform.rate_limit import get_rate_limiter, check_tenant_llm_budget
        ok = get_rate_limiter().allow(
            f"tg:{int(user_id)}",
            limit=RATE_LIMIT_PER_MINUTE,
            window_sec=RATE_LIMIT_WINDOW_SECONDS,
        )
        if not ok:
            return False
        # Hard LLM budget (tokens/USD daily) — refuse before expensive model calls.
        budget_ok, _reason = check_tenant_llm_budget(f"tg:{int(user_id)}", add_tokens=0, add_usd=0.0)
        return bool(budget_ok)
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


def generation_backpressure_ok(user_id: int) -> tuple[bool, str]:
    """Reject when generation queue is saturated (low-and-slow defense)."""
    try:
        from b2b_platform.queue_backpressure import check_enqueue_allowed
        return check_enqueue_allowed(f"tg:{int(user_id)}", kind="generate")
    except Exception:
        import os
        if (os.getenv("ENVIRONMENT") or "").strip().lower() in {"production", "prod", "staging"}:
            return False, "backpressure_unavailable"
        return True, "ok"
