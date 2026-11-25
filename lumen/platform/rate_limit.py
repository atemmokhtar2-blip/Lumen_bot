"""Rate limiter — Redis preferred, process-local fallback for budget.

REDIS_URL is preferred for multi-worker deployments. When Redis is not
configured, the LLM hard-budget gate falls back to process-local daily
counters (thread-safe), which is correct for single-process deployments.

Callers use RateLimiter only — never branch on backend type.
"""
from __future__ import annotations

import logging
import math
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
        from lumen.platform.redis_client import connect_redis_url

        self._r = connect_redis_url(
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


_LLM_BUDGET_LUA = """
local tok_key = KEYS[1]
local usd_key = KEYS[2]
local tok_cap = tonumber(ARGV[1])
local usd_cap_micro = tonumber(ARGV[2])
local add_tok = tonumber(ARGV[3])
local add_usd_micro = tonumber(ARGV[4])
local ttl = tonumber(ARGV[5])

local cur_tok = math.max(0, tonumber(redis.call("GET", tok_key) or "0"))
local cur_usd = math.max(0, tonumber(redis.call("GET", usd_key) or "0"))
local cur_usd_micro = math.floor(cur_usd * 1000000 + 0.5)

-- Check both budgets and reserve both amounts in one Redis transaction.
if tok_cap > 0 and cur_tok + add_tok > tok_cap then
  return {0, cur_tok, string.format("%.6f", cur_usd), 1}
end
if usd_cap_micro > 0 and cur_usd_micro + add_usd_micro > usd_cap_micro then
  return {0, cur_tok, string.format("%.6f", cur_usd), 2}
end

if add_tok > 0 then
  redis.call("INCRBY", tok_key, add_tok)
  redis.call("EXPIRE", tok_key, ttl)
end
if add_usd_micro > 0 then
  local next_usd_micro = cur_usd_micro + add_usd_micro
  redis.call("SET", usd_key, string.format("%.6f", next_usd_micro / 1000000), "EX", ttl)
end

return {1, cur_tok + add_tok, string.format("%.6f", (cur_usd_micro + add_usd_micro) / 1000000), 0}
"""


def check_tenant_llm_budget(
    tenant_id: str,
    *,
    add_tokens: int = 0,
    add_usd: float = 0.0,
) -> tuple[bool, str]:
    """Atomically reserve daily token and USD budget for one tenant.

    Redis performs the read/check/increment in one Lua script, so concurrent
    workers cannot both spend the same remaining budget. The single-process
    fallback is protected by a lock and is only suitable for local development.
    """
    tid = "".join(ch if ch.isalnum() or ch in "-_" else "_" for ch in str(tenant_id or "anon"))[:80]
    tok_cap, usd_cap = _budget_defaults()
    try:
        # Budget checks are reservations, never refunds: negative or non-finite
        # caller values must not decrement counters or bypass a cap.
        add_tokens = max(0, int(add_tokens))
        usd_amount = float(add_usd)
        if not math.isfinite(usd_amount):
            return False, "invalid_llm_budget_amount"
        add_usd = max(0.0, usd_amount)
    except (TypeError, ValueError, OverflowError):
        return False, "invalid_llm_budget_amount"

    if add_tokens > (2**53 - 1) or add_usd > 1_000_000_000_000:
        return False, "invalid_llm_budget_amount"
    add_usd_micro = int(round(add_usd * 1_000_000))
    usd_cap_micro = int(round(usd_cap * 1_000_000))
    if tok_cap <= 0 and usd_cap_micro <= 0:
        return True, "ok"

    day = time.strftime("%Y%m%d", time.gmtime())
    tok_key = f"llm_tok:{tid}:{day}"
    usd_key = f"llm_usd:{tid}:{day}"

    try:
        from .runtime_config import is_dev as _is_dev, redis_url as _redis_url_fn
        url = (_redis_url_fn() or "").strip()
        dev_mode = bool(_is_dev())
    except Exception:
        url = (os.getenv("REDIS_URL") or os.getenv("JOB_REDIS_URL") or "").strip()
        dev_mode = (os.getenv("ENVIRONMENT") or os.getenv("TBE_ENV") or "").strip().lower() in {
            "dev", "development", "local", "test"
        }

    if url:
        try:
            from lumen.platform.redis_client import connect_redis_url
            r = connect_redis_url(
                url,
                decode_responses=True,
                socket_connect_timeout=float(os.getenv("REDIS_CONNECT_TIMEOUT") or "5"),
                socket_timeout=float(os.getenv("REDIS_SOCKET_TIMEOUT") or "5"),
            )
            result = r.eval(
                _LLM_BUDGET_LUA,
                2,
                tok_key,
                usd_key,
                int(tok_cap),
                usd_cap_micro,
                add_tokens,
                add_usd_micro,
                48 * 3600,
            )
            allowed = int(result[0])
            current_tokens = int(float(result[1]))
            current_usd = float(result[2])
            reason_code = int(result[3])
            if not allowed:
                if reason_code == 1:
                    return False, f"llm_token_cap_exceeded:{current_tokens}/{tok_cap}"
                return False, f"llm_usd_cap_exceeded:{current_usd:.4f}/{usd_cap}"
            return True, "ok"
        except Exception:
            logger.warning("llm budget redis failed; refusing", exc_info=True)
            return False, "llm_budget_backend_unavailable"

    # Never use per-process accounting in production: multiple replicas would
    # each get an independent allowance and could multiply the tenant's budget.
    if not dev_mode:
        return False, "llm_budget_backend_required"

    # No Redis: the lock in _in_process_budget_check makes this atomic only
    # within one process; this fallback is explicitly development/test only.
    return _in_process_budget_check(
        tid, day, tok_key, usd_key, tok_cap, usd_cap, add_tokens, add_usd
    )


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
