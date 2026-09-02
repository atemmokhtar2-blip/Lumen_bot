"""Host-plane rate limits — concurrent projects and start RPM per user/tenant.

Config:
  TBE_HOST_MAX_CONCURRENT_PER_USER=5
  TBE_HOST_MAX_STARTS_PER_HOUR=20
  Plan overrides via metering/billing when available.
"""
from __future__ import annotations

import logging
import os
import time
from collections import defaultdict, deque
from threading import Lock
from typing import Deque

logger = logging.getLogger("tbe.hosting.rate_limiter")

_lock = Lock()
_starts: dict[int, Deque[float]] = defaultdict(deque)


def max_concurrent(user_id: int = 0, tenant_id: str | None = None) -> int:
    # Plan hosted_bots (credits product still exposes a soft concurrent cap)
    try:
        from lumen.platform.plans import get_plan
        plan_cap = int(getattr(get_plan(None), "hosted_bots", 0) or 0)
        if 0 < plan_cap < 10**8:
            env_cap = int((os.environ.get("TBE_HOST_MAX_CONCURRENT_PER_USER") or str(plan_cap)).strip())
            return max(1, min(plan_cap, env_cap) if env_cap else plan_cap)
    except Exception:
        pass
    try:
        return max(1, int((os.environ.get("TBE_HOST_MAX_CONCURRENT_PER_USER") or "5").strip()))
    except Exception:
        return 5



def max_starts_per_hour(user_id: int = 0) -> int:
    try:
        return max(1, int((os.environ.get("TBE_HOST_MAX_STARTS_PER_HOUR") or "20").strip()))
    except Exception:
        return 20


def check_can_start(*, user_id: int, running_count: int, tenant_id: str | None = None) -> tuple[bool, str]:
    """Return (ok, reason)."""
    uid = int(user_id or 0)
    lim_c = max_concurrent(uid, tenant_id=tenant_id)
    if running_count >= lim_c:
        return False, f"host_concurrent_limit:{running_count}>={lim_c}"
    lim_h = max_starts_per_hour(uid)
    now = time.time()
    with _lock:
        q = _starts[uid]
        while q and now - q[0] > 3600:
            q.popleft()
        if len(q) >= lim_h:
            return False, f"host_starts_per_hour_limit:{len(q)}>={lim_h}"
    return True, "ok"


def record_start(user_id: int) -> None:
    with _lock:
        _starts[int(user_id or 0)].append(time.time())


__all__ = [
    "check_can_start",
    "record_start",
    "max_concurrent",
    "max_starts_per_hour",
]
