"""Phase E — process-wide concurrency limit for orchestrations (safe parallelism)."""
from __future__ import annotations

import os
import threading
from contextlib import contextmanager
from typing import Iterator


def _limit() -> int:
    try:
        return max(1, min(32, int(os.environ.get("MULTI_AGENT_MAX_CONCURRENT") or "4")))
    except ValueError:
        return 4


_SEM = threading.Semaphore(_limit())
_ACTIVE = 0
_ACTIVE_LOCK = threading.Lock()


@contextmanager
def orchestration_slot(timeout: float | None = None) -> Iterator[bool]:
    """Acquire a global slot; yields False if timeout without acquire."""
    global _ACTIVE
    to = timeout
    if to is None:
        try:
            to = float(os.environ.get("MULTI_AGENT_SLOT_TIMEOUT_SEC") or "120")
        except ValueError:
            to = 120.0
    got = _SEM.acquire(timeout=max(0.1, to))
    if not got:
        yield False
        return
    with _ACTIVE_LOCK:
        _ACTIVE += 1
    try:
        yield True
    finally:
        with _ACTIVE_LOCK:
            _ACTIVE = max(0, _ACTIVE - 1)
        _SEM.release()


def active_count() -> int:
    with _ACTIVE_LOCK:
        return _ACTIVE
