"""Rate limiter — Redis preferred, process-local fallback for budget.

REDIS_URL is preferred for multi-worker deployments. When Redis is not
configured, the LLM hard-budget gate falls back to process-local daily
counters (thread-safe), which is correct for single-process deployments.

Callers use RateLimiter only — never branch on backend type.
"""
from __future__ import annotations

import logging
import os
import threading
import time
from pathlib import Path
from typing import Protocol

logger = logging.getLogger("lumen.rate_limit")


class RateLimiterBackend(Protocol):
    def allow(self, key: str, *, limit: int, window_sec: float = 60.0) -> bool: ...
    def remaining(self, key: str, *, limit: int, window_sec: float = 60.0) -> int: ...
    def seconds_until_allow(self, key: str, *, limit: int, window_sec: float = 60.0) -> int: ...


# ── Redis backend ────────────────────────────────────────────────────────────

class RedisRateLimiter:
    """Sliding-window rate limiter using Redis sorted sets.

    Each hit is a member scored by timestamp. Old members are trimmed on
    every check. Works correctly across multiple API workers/processes.
    """

    def __init__(self, redis_url: str) -> None:
        import redis  # optional dependency; imported only when configured

        connect_to = float(os.getenv("REDIS_CONNECT_TIMEOUT") or "2")
        socket_to = float(os.getenv("REDIS_SOCKET_TIMEOUT") or "2")
        self._r = redis.Redis.from_url(
            redis_url,
            decode_responses=True,
            socket_connect_timeout=connect_to,
            socket_timeout=socket_to,
        )
        # Fail fast if Redis is unreachable at construction time
        self._r.ping()
        self._prefix = (os.getenv("REDIS_RATE_PREFIX") or "rl:").strip() or "rl:"

    def _key(self, key: str) -> str:
        return f"{self._prefix}{key}"

    # Atomic sliding-window: ZREMRANGEBYSCORE + ZCARD + conditional ZADD in one Lua script
    _ALLOW_LUA = """
    local key = KEYS[1]
    local now = tonumber(ARGV[1])
    local cutoff = tonumber(ARGV[2])
    local limit = tonumber(ARGV[3])
    local member = ARGV[4]
    local ttl = tonumber(ARGV[5])
    redis.call('ZREMRANGEBYSCORE', key, 0, cutoff)
    local count = redis.call('ZCARD', key)
    if count >= limit then
      return 0
    end
    redis.call('ZADD', key, now, member)
    redis.call('EXPIRE', key, ttl)
    return 1
    """

    def allow(self, key: str, *, limit: int, window_sec: float = 60.0) -> bool:
        if limit <= 0:
            return True
        now = time.time()
        cutoff = now - window_sec
        rk = self._key(key)
        member = f"{now}:{threading.get_ident()}:{id(object())}"
        ttl = int(window_sec) + 5
        allowed = self._r.eval(
            self._ALLOW_LUA, 1, rk, str(now), str(cutoff), str(limit), member, str(ttl)
        )
        return bool(int(allowed or 0))

    def remaining(self, key: str, *, limit: int, window_sec: float = 60.0) -> int:
        if limit <= 0:
            return 10**9
        now = time.time()
        cutoff = now - window_sec
        rk = self._key(key)
        self._r.zremrangebyscore(rk, 0, cutoff)
        used = int(self._r.zcard(rk) or 0)
        return max(0, limit - used)

    def seconds_until_allow(self, key: str, *, limit: int, window_sec: float = 60.0) -> int:
        if limit <= 0:
            return 0
        now = time.time()
        cutoff = now - window_sec
        rk = self._key(key)
        self._r.zremrangebyscore(rk, 0, cutoff)
        members = self._r.zrange(rk, 0, 0, withscores=True)
        count = int(self._r.zcard(rk) or 0)
        if count < limit:
            return 0
        if not members:
            return 0
        oldest = float(members[0][1])
        return max(1, int(oldest + window_sec - now) + 1)


# ── Public facade (Redis only) ──────────────────────────────────────────────


class RateLimiter:
    """Facade: Redis-only rate limiting (exact multi-worker limits)."""

    def __init__(self) -> None:
        self._backend: RateLimiterBackend = self._select_backend()

    @staticmethod
    def _select_backend() -> RateLimiterBackend:
        """Redis is mandatory in every environment — no Memory/SQLite fallback.

        Lab/tests must provide REDIS_URL (e.g. docker run redis). Mis-set
        ENVIRONMENT=dev must never open a multi-worker DoS hole.
        """
        from .runtime_config import redis_url
        url = (redis_url() or "").strip()
        if not url:
            raise RuntimeError(
                "REDIS_URL is required for rate limiting (no local fallback). "
                "Start Redis for lab: docker run -p 6379:6379 redis:7-alpine"
            )
        try:
            backend = RedisRateLimiter(url)
        except Exception as exc:
            raise RuntimeError(
                f"Redis rate limiter unavailable: {type(exc).__name__}: {exc}. "
                "No Memory/SQLite fallback is permitted."
            ) from exc
        logger.info("rate_limit backend=redis")
        return backend

    def allow(self, key: str, *, limit: int, window_sec: float = 60.0) -> bool:
        return self._backend.allow(key, limit=limit, window_sec=window_sec)

    def remaining(self, key: str, *, limit: int, window_sec: float = 60.0) -> int:
        return self._backend.remaining(key, limit=limit, window_sec=window_sec)

    def seconds_until_allow(self, key: str, *, limit: int, window_sec: float = 60.0) -> int:
        return self._backend.seconds_until_allow(key, limit=limit, window_sec=window_sec)


_LIMITER: RateLimiter | None = None


def get_rate_limiter() -> RateLimiter:
    global _LIMITER
    if _LIMITER is None:
        _LIMITER = RateLimiter()
    return _LIMITER


# ── Tenant LLM hard budget (tokens / estimated USD) ───────────────────────────
# Soft RPM alone cannot stop LLM cost burn. These hard caps refuse the request
# immediately when daily token or USD budget is exhausted.

def _budget_defaults() -> tuple[int, float]:
    try:
        tokens = int(os.getenv("TENANT_LLM_TOKEN_DAILY_CAP") or "500000")
    except ValueError:
        tokens = 500_000
    try:
        usd = float(os.getenv("TENANT_LLM_USD_DAILY_CAP") or "25")
    except ValueError:
        usd = 25.0
    return max(0, tokens), max(0.0, usd)


def check_tenant_llm_budget(
    tenant_id: str,
    *,
    add_tokens: int = 0,
    add_usd: float = 0.0,
) -> tuple[bool, str]:
    """Hard-cap daily LLM usage per tenant. Returns (allowed, reason).

    Uses Redis when available; process-local counters in pure dev only.
    add_* are reserved/consumed only when the call is allowed.
    """
    tid = "".join(ch if ch.isalnum() or ch in "-_" else "_" for ch in str(tenant_id or "anon"))[:80]
    tok_cap, usd_cap = _budget_defaults()
    if tok_cap <= 0 and usd_cap <= 0:
        return True, "budget_disabled"

    day = time.strftime("%Y%m%d", time.gmtime())
    tok_key = f"llm_tok:{tid}:{day}"
    usd_key = f"llm_usd:{tid}:{day}"

    # Try Redis atomic INCR
    try:
        from .runtime_config import redis_url as _redis_url_fn

        url = (_redis_url_fn() or "").strip()
    except Exception:
        url = (os.getenv("REDIS_URL") or os.getenv("JOB_REDIS_URL") or "").strip()
    if url:
        try:
            import redis
            r = redis.Redis.from_url(
                url,
                decode_responses=True,
                socket_connect_timeout=float(os.getenv("REDIS_CONNECT_TIMEOUT") or "5"),
                socket_timeout=float(os.getenv("REDIS_SOCKET_TIMEOUT") or "5"),
            )
            pipe = r.pipeline()
            pipe.get(tok_key)
            pipe.get(usd_key)
            cur_tok_s, cur_usd_s = pipe.execute()
            cur_tok = int(float(cur_tok_s or 0))
            cur_usd = float(cur_usd_s or 0)
            if tok_cap > 0 and cur_tok + max(0, int(add_tokens)) > tok_cap:
                return False, f"llm_token_cap_exceeded:{cur_tok}/{tok_cap}"
            if usd_cap > 0 and cur_usd + max(0.0, float(add_usd)) > usd_cap:
                return False, f"llm_usd_cap_exceeded:{cur_usd:.4f}/{usd_cap}"
            if add_tokens or add_usd:
                pipe = r.pipeline()
                if add_tokens:
                    pipe.incrby(tok_key, int(add_tokens))
                    pipe.expire(tok_key, 48 * 3600)
                if add_usd:
                    pipe.incrbyfloat(usd_key, float(add_usd))
                    pipe.expire(usd_key, 48 * 3600)
                pipe.execute()
            return True, "ok"
        except Exception:
            logger.warning("llm budget redis failed; refusing", exc_info=True)
            return False, "llm_budget_backend_unavailable"

    # No Redis: fall back to process-local daily counters.
    # Safe for single-process deployments (the common Telegram-bot case).
    # Multi-worker deployments should set REDIS_URL for shared accounting.
    return _in_process_budget_check(tid, day, tok_key, usd_key, tok_cap, usd_cap, add_tokens, add_usd)


# ── Process-local LLM budget (fallback when Redis is unavailable) ──────────────
_PROC_BUDGET_LOCK = threading.Lock()
_PROC_BUDGET: dict[str, dict[str, float]] = {}  # tid -> {"tokens": float, "usd": float}


def _in_process_budget_check(
    tid: str,
    day: str,
    tok_key: str,
    usd_key: str,
    tok_cap: int,
    usd_cap: float,
    add_tokens: int,
    add_usd: float,
) -> tuple[bool, str]:
    """Thread-safe in-process daily budget counters (no Redis needed)."""
    # Daily reset: keys include the day so stale entries are naturally ignored,
    # but we also prune entries from previous days to bound memory.
    with _PROC_BUDGET_LOCK:
        # Prune entries from previous days (keep only today's)
        today_prefix = f"{tid}:{day}"
        stale = [k for k in _PROC_BUDGET if not k.endswith(today_prefix) and tid in k]
        for k in stale:
            _PROC_BUDGET.pop(k, None)
        entry = _PROC_BUDGET.setdefault(today_prefix, {"tokens": 0.0, "usd": 0.0})
        cur_tok = int(entry["tokens"])
        cur_usd = float(entry["usd"])
        if tok_cap > 0 and cur_tok + max(0, int(add_tokens)) > tok_cap:
            return False, f"llm_token_cap_exceeded:{cur_tok}/{tok_cap}"
        if usd_cap > 0 and cur_usd + max(0.0, float(add_usd)) > usd_cap:
            return False, f"llm_usd_cap_exceeded:{cur_usd:.4f}/{usd_cap}"
        if add_tokens:
            entry["tokens"] = cur_tok + int(add_tokens)
        if add_usd:
            entry["usd"] = cur_usd + float(add_usd)
        return True, "ok_proc"
