"""Phase E — global + per-user concurrency limits."""
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


def _per_user_limit() -> int:
    try:
        return max(1, min(8, int(os.environ.get("MULTI_AGENT_MAX_PER_USER") or "2")))
    except ValueError:
        return 2


_SEM = threading.Semaphore(_limit())
_ACTIVE = 0
_ACTIVE_LOCK = threading.Lock()
_USER_ACTIVE: dict[int, int] = {}


@contextmanager
def orchestration_slot(timeout: float | None = None, *, user_id: int = 0) -> Iterator[bool]:
    global _ACTIVE
    to = timeout
    if to is None:
        try:
            to = float(os.environ.get("MULTI_AGENT_SLOT_TIMEOUT_SEC") or "120")
        except ValueError:
            to = 120.0

    # per-user gate first
    uid = int(user_id or 0)
    with _ACTIVE_LOCK:
        cur = _USER_ACTIVE.get(uid, 0)
        if uid and cur >= _per_user_limit():
            yield False
            return
        if uid:
            _USER_ACTIVE[uid] = cur + 1

    got = _SEM.acquire(timeout=max(0.1, to))
    if not got:
        with _ACTIVE_LOCK:
            if uid:
                _USER_ACTIVE[uid] = max(0, _USER_ACTIVE.get(uid, 1) - 1)
                if _USER_ACTIVE.get(uid) == 0:
                    _USER_ACTIVE.pop(uid, None)
        yield False
        return

    with _ACTIVE_LOCK:
        _ACTIVE += 1
    try:
        yield True
    finally:
        with _ACTIVE_LOCK:
            _ACTIVE = max(0, _ACTIVE - 1)
            if uid:
                _USER_ACTIVE[uid] = max(0, _USER_ACTIVE.get(uid, 1) - 1)
                if _USER_ACTIVE.get(uid) == 0:
                    _USER_ACTIVE.pop(uid, None)
        _SEM.release()


def active_count() -> int:
    with _ACTIVE_LOCK:
        return _ACTIVE


def active_by_user() -> dict[int, int]:
    with _ACTIVE_LOCK:
        return dict(_USER_ACTIVE)
