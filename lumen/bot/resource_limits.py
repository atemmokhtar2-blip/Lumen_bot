"""Hard resource limits for Telegram bot + engine calls.

Prevents RAM / CPU exhaustion before rate-limiter intervention.
Uses stdlib only (concurrent.futures) — not a fake script.
"""
from __future__ import annotations

import concurrent.futures
import os
from typing import Any, Callable, TypeVar

T = TypeVar("T")

# Inbound user text (Telegram allows ~4096; we cap lower for LLM cost)
MAX_USER_MESSAGE_CHARS = int(os.getenv("MAX_USER_MESSAGE_CHARS") or "4000")
# Spec / generation request body
MAX_SPEC_REQUEST_CHARS = int(os.getenv("MAX_SPEC_REQUEST_CHARS") or "12000")
# Hard wall-clock for expensive engine work (translate + generate)
ENGINE_TIMEOUT_SEC = float(os.getenv("ENGINE_TIMEOUT_SEC") or "30")


def clamp_user_text(text: str, *, limit: int | None = None) -> str:
    """Truncate inbound user text to a safe maximum."""
    lim = int(limit if limit is not None else MAX_USER_MESSAGE_CHARS)
    lim = max(64, min(lim, 32000))
    s = str(text or "")
    if len(s) <= lim:
        return s
    return s[:lim]


def clamp_spec_request(text: str) -> str:
    return clamp_user_text(text, limit=MAX_SPEC_REQUEST_CHARS)


class EngineTimeoutError(TimeoutError):
    """Engine call exceeded ENGINE_TIMEOUT_SEC."""


def run_with_engine_timeout(
    fn: Callable[..., T],
    /,
    *args: Any,
    timeout: float | None = None,
    **kwargs: Any,
) -> T:
    """Run callable with a hard wall-clock timeout (thread pool).

    Note: cooperative only for pure-Python work; native C extensions may
    still run until completion, but the caller stops waiting and can refuse
    to continue the request path.
    """
    sec = float(timeout if timeout is not None else ENGINE_TIMEOUT_SEC)
    sec = max(1.0, min(sec, 300.0))
    # Do NOT wait on shutdown — a hung worker must not pin the request thread
    pool = concurrent.futures.ThreadPoolExecutor(max_workers=1)
    try:
        fut = pool.submit(fn, *args, **kwargs)
        try:
            return fut.result(timeout=sec)
        except concurrent.futures.TimeoutError as exc:
            fut.cancel()
            raise EngineTimeoutError(
                f"engine exceeded {sec:.0f}s wall-clock limit"
            ) from exc
    finally:
        try:
            pool.shutdown(wait=False, cancel_futures=True)
        except TypeError:
            # Python <3.9: cancel_futures unsupported
            pool.shutdown(wait=False)
