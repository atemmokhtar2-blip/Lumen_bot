"""Global + per-tenant queue backpressure for generation / LLM jobs.

Blocks low-and-slow exhaustion when rate limits alone are insufficient:
  - Max concurrent in-flight generations (process / Redis)
  - Max queued jobs depth
  - Per-tenant concurrent cap
"""
from __future__ import annotations

import logging
import os
import threading
import time
from typing import Any

logger = logging.getLogger("b2b.queue_backpressure")

_lock = threading.Lock()
_inflight = 0
_inflight_by_tenant: dict[str, int] = {}


def _max_global() -> int:
    try:
        return max(1, int(os.getenv("TBE_MAX_INFLIGHT_GENERATIONS") or "8"))
    except ValueError:
        return 8


def _max_queue_depth() -> int:
    try:
        return max(1, int(os.getenv("TBE_MAX_QUEUE_DEPTH") or "50"))
    except ValueError:
        return 50


def _max_per_tenant() -> int:
    try:
        return max(1, int(os.getenv("TBE_MAX_TENANT_INFLIGHT") or "2"))
    except ValueError:
        return 2


def _redis():
    url = (os.getenv("JOB_REDIS_URL") or os.getenv("REDIS_URL") or "").strip()
    if not url:
        return None
    try:
        import redis
        return redis.Redis.from_url(url, socket_connect_timeout=2, socket_timeout=2)
    except Exception:
        return None


def check_enqueue_allowed(tenant_id: str, *, kind: str = "generate") -> tuple[bool, str]:
    """Fail closed when queue is saturated."""
    tid = str(tenant_id or "anon").strip() or "anon"
    r = _redis()
    if r is not None:
        try:
            # RQ queue length
            qname = (os.getenv("RQ_QUEUE_NAME") or "tbe").strip() or "tbe"
            depth = int(r.llen(f"rq:queue:{qname}") or 0)
            if depth >= _max_queue_depth():
                return False, f"queue_depth_exceeded:{depth}"
            gkey = "tbe:bp:inflight"
            tkey = f"tbe:bp:inflight:{tid}"
            g = int(r.get(gkey) or 0)
            t = int(r.get(tkey) or 0)
            if g >= _max_global():
                return False, f"global_inflight_exceeded:{g}"
            if t >= _max_per_tenant():
                return False, f"tenant_inflight_exceeded:{t}"
            return True, "ok"
        except Exception as exc:
            logger.warning("redis backpressure check failed: %s", type(exc).__name__)
            # fall through to memory

    with _lock:
        if _inflight >= _max_global():
            return False, f"global_inflight_exceeded:{_inflight}"
        if _inflight_by_tenant.get(tid, 0) >= _max_per_tenant():
            return False, f"tenant_inflight_exceeded:{_inflight_by_tenant.get(tid, 0)}"
    return True, "ok"


def acquire_slot(tenant_id: str) -> tuple[bool, str]:
    """Reserve an in-flight slot. Pair with release_slot in finally."""
    ok, reason = check_enqueue_allowed(tenant_id)
    if not ok:
        return False, reason
    tid = str(tenant_id or "anon").strip() or "anon"
    r = _redis()
    if r is not None:
        try:
            gkey = "tbe:bp:inflight"
            tkey = f"tbe:bp:inflight:{tid}"
            pipe = r.pipeline()
            pipe.incr(gkey)
            pipe.expire(gkey, 3600)
            pipe.incr(tkey)
            pipe.expire(tkey, 3600)
            pipe.execute()
            return True, "ok"
        except Exception:
            pass
    global _inflight
    with _lock:
        _inflight += 1
        _inflight_by_tenant[tid] = _inflight_by_tenant.get(tid, 0) + 1
    return True, "ok"


def release_slot(tenant_id: str) -> None:
    tid = str(tenant_id or "anon").strip() or "anon"
    r = _redis()
    if r is not None:
        try:
            gkey = "tbe:bp:inflight"
            tkey = f"tbe:bp:inflight:{tid}"
            pipe = r.pipeline()
            pipe.decr(gkey)
            pipe.decr(tkey)
            pipe.execute()
            # floor at 0
            if int(r.get(gkey) or 0) < 0:
                r.set(gkey, 0)
            if int(r.get(tkey) or 0) < 0:
                r.set(tkey, 0)
            return
        except Exception:
            pass
    global _inflight
    with _lock:
        _inflight = max(0, _inflight - 1)
        _inflight_by_tenant[tid] = max(0, _inflight_by_tenant.get(tid, 0) - 1)
