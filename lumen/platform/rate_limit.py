"""Rate limiter — Redis mandatory in production; local only in explicit dev.

Foundation:
  - Production / staging: REDIS_URL required. No SQLite / memory fallback
    (multi-worker DoS hole if local backends are used under B2B load).
  - Dev / local / test: SQLite or in-process memory allowed when Redis is absent.
  - Every backend is fronted by a process-local token-bucket (first layer) to
    absorb bursts before hitting Redis/SQLite.

Callers use RateLimiter only — never branch on backend type.
"""
from __future__ import annotations

import logging
import os
import sqlite3
import threading
import time
from pathlib import Path
from typing import Protocol

logger = logging.getLogger("lumen.rate_limit")

def _durable_data_dir() -> Path:
    try:
        from .paths import durable_data_dir
        return durable_data_dir()
    except Exception:
        p = Path.home() / ".lumen"
        p.mkdir(parents=True, exist_ok=True)
        return p



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

        self._r = redis.Redis.from_url(redis_url, decode_responses=True)
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


# ── SQLite backend (fallback) ────────────────────────────────────────────────

class SqliteRateLimiter:
    """Process-safe rate limiter backed by SQLite — **dev only**.

    Construction outside ENVIRONMENT=dev|local|test raises. Production must use Redis.
    """

    def __init__(self, db_path: str | Path | None = None) -> None:
        from .runtime_config import is_dev
        if not is_dev():
            raise RuntimeError(
                "SqliteRateLimiter is forbidden outside ENVIRONMENT=dev|local|test. "
                "Set REDIS_URL for production rate limiting."
            )
        base = _durable_data_dir()
        self.path = Path(db_path or (base / "platform" / "rate_limit.sqlite3"))
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._local = threading.local()
        self._init_db()

    def _conn(self) -> sqlite3.Connection:
        conn = getattr(self._local, "conn", None)
        if conn is None:
            conn = sqlite3.connect(str(self.path), timeout=30, check_same_thread=False)
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA synchronous=NORMAL")
            self._local.conn = conn
        return conn

    def _init_db(self) -> None:
        with self._conn() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS hits (
                    bucket TEXT NOT NULL,
                    ts REAL NOT NULL
                )
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_hits_bucket_ts ON hits(bucket, ts)"
            )
            conn.commit()

    def allow(self, key: str, *, limit: int, window_sec: float = 60.0) -> bool:
        if limit <= 0:
            return True
        now = time.time()
        cutoff = now - window_sec
        bucket = str(key)
        conn = self._conn()
        with conn:
            conn.execute("DELETE FROM hits WHERE bucket=? AND ts < ?", (bucket, cutoff))
            row = conn.execute(
                "SELECT COUNT(*) FROM hits WHERE bucket=?", (bucket,)
            ).fetchone()
            count = int(row[0]) if row else 0
            if count >= limit:
                return False
            conn.execute("INSERT INTO hits(bucket, ts) VALUES (?, ?)", (bucket, now))
        return True

    def remaining(self, key: str, *, limit: int, window_sec: float = 60.0) -> int:
        if limit <= 0:
            return 10**9
        now = time.time()
        cutoff = now - window_sec
        conn = self._conn()
        row = conn.execute(
            "SELECT COUNT(*) FROM hits WHERE bucket=? AND ts >= ?",
            (str(key), cutoff),
        ).fetchone()
        used = int(row[0]) if row else 0
        return max(0, limit - used)

    def seconds_until_allow(self, key: str, *, limit: int, window_sec: float = 60.0) -> int:
        if limit <= 0:
            return 0
        now = time.time()
        cutoff = now - window_sec
        conn = self._conn()
        rows = conn.execute(
            "SELECT ts FROM hits WHERE bucket=? AND ts >= ? ORDER BY ts ASC",
            (str(key), cutoff),
        ).fetchall()
        if len(rows) < limit:
            return 0
        oldest = float(rows[0][0])
        return max(1, int(oldest + window_sec - now) + 1)


# ── Public facade ────────────────────────────────────────────────────────────


class MemoryRateLimiter:
    """Process-local sliding window — always available emergency backend."""

    def __init__(self) -> None:
        self._hits: dict[str, list[float]] = {}
        self._lock = threading.Lock()

    def allow(self, key: str, *, limit: int, window_sec: float = 60.0) -> bool:
        if limit <= 0:
            return True
        now = time.time()
        cutoff = now - window_sec
        with self._lock:
            bucket = [ts for ts in self._hits.get(key, []) if ts >= cutoff]
            if len(bucket) >= limit:
                self._hits[key] = bucket
                return False
            bucket.append(now)
            self._hits[key] = bucket
            # opportunistic prune
            if len(self._hits) > 20000:
                stale = [k for k, v in self._hits.items() if not v or v[-1] < cutoff]
                for k in stale[:5000]:
                    self._hits.pop(k, None)
            return True

    def remaining(self, key: str, *, limit: int, window_sec: float = 60.0) -> int:
        if limit <= 0:
            return 10**9
        now = time.time()
        cutoff = now - window_sec
        with self._lock:
            bucket = [ts for ts in self._hits.get(key, []) if ts >= cutoff]
            self._hits[key] = bucket
            return max(0, limit - len(bucket))

    def seconds_until_allow(self, key: str, *, limit: int, window_sec: float = 60.0) -> int:
        if limit <= 0:
            return 0
        now = time.time()
        cutoff = now - window_sec
        with self._lock:
            bucket = sorted(ts for ts in self._hits.get(key, []) if ts >= cutoff)
            if len(bucket) < limit:
                return 0
            oldest = bucket[0]
            return max(1, int(oldest + window_sec - now) + 1)


class LocalTokenBucket:
    """Process-local token bucket — first defense layer before Redis/SQLite.

    Not a multi-worker authority (that is Redis). Absorbs intra-process bursts
    and fails closed under extreme local load without opening DB locks.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        # key -> (tokens, last_refill_monotonic)
        self._buckets: dict[str, tuple[float, float]] = {}

    def allow(self, key: str, *, limit: int, window_sec: float = 60.0) -> bool:
        if limit <= 0:
            return True
        rate = max(0.01, float(limit) / max(0.1, float(window_sec)))
        capacity = float(max(1, limit))
        now = time.monotonic()
        with self._lock:
            tokens, last = self._buckets.get(key, (capacity, now))
            elapsed = max(0.0, now - last)
            tokens = min(capacity, tokens + elapsed * rate)
            if tokens < 1.0:
                self._buckets[key] = (tokens, now)
                return False
            self._buckets[key] = (tokens - 1.0, now)
            return True


class RateLimiter:
    """Facade: Redis mandatory outside dev; local backends only when ENVIRONMENT=dev.

    Layering: LocalTokenBucket (process) → Redis/SQLite backend (shared).
    """

    def __init__(self) -> None:
        self._local = LocalTokenBucket()
        self._backend: RateLimiterBackend = self._select_backend()

    @staticmethod
    def _select_backend() -> RateLimiterBackend:
        from .runtime_config import redis_url, is_dev
        url = redis_url()
        if url:
            try:
                backend = RedisRateLimiter(url)
                logger.info("rate_limit backend=redis")
                return backend
            except Exception as exc:
                # Production: NEVER fall back to memory/sqlite (multi-worker DDoS hole)
                if not is_dev():
                    raise RuntimeError(
                        f"Redis rate limiter unavailable in production: {type(exc).__name__}: {exc}. "
                        "Refusing to start with local fallback."
                    ) from exc
                logger.warning("Redis rate limiter failed in dev (%s); using memory", exc)
                return MemoryRateLimiter()
        if is_dev():
            try:
                logger.info("rate_limit backend=sqlite (dev only — never production)")
                return SqliteRateLimiter()
            except Exception:
                return MemoryRateLimiter()
        raise RuntimeError(
            "REDIS_URL is required for rate limiting outside ENVIRONMENT=dev. "
            "No MemoryRateLimiter / SQLite fallback in production (B2B multi-tenant DoS risk)."
        )

    def allow(self, key: str, *, limit: int, window_sec: float = 60.0) -> bool:
        # First layer: process-local token bucket
        if not self._local.allow(key, limit=limit, window_sec=window_sec):
            return False
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
    url = (os.getenv("REDIS_URL") or os.getenv("JOB_REDIS_URL") or "").strip()
    if url:
        try:
            import redis
            r = redis.Redis.from_url(url, decode_responses=True)
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
            logger.warning("llm budget redis failed; refusing in non-dev", exc_info=True)
            env = (os.getenv("ENVIRONMENT") or os.getenv("TBE_ENV") or "").strip().lower()
            if env not in {"dev", "development", "local", "test"}:
                return False, "llm_budget_backend_unavailable"
            # fall through to memory in dev

    # Dev memory fallback
    store = getattr(check_tenant_llm_budget, "_mem", None)
    if store is None:
        store = {}
        check_tenant_llm_budget._mem = store  # type: ignore[attr-defined]
    cur_tok, cur_usd = store.get(tok_key, (0, 0.0))
    if tok_cap > 0 and cur_tok + max(0, int(add_tokens)) > tok_cap:
        return False, f"llm_token_cap_exceeded:{cur_tok}/{tok_cap}"
    if usd_cap > 0 and cur_usd + max(0.0, float(add_usd)) > usd_cap:
        return False, f"llm_usd_cap_exceeded:{cur_usd:.4f}/{usd_cap}"
    store[tok_key] = (cur_tok + max(0, int(add_tokens)), cur_usd + max(0.0, float(add_usd)))
    return True, "ok"
