"""Rate limiter — Redis-first, SQLite fallback.

Foundation:
  - When REDIS_URL is set and reachable → Redis sliding-window counters.
  - Otherwise → process-safe SQLite (WAL) for single-node / local dev.

Both backends share the same RateLimiter interface so callers never branch.
"""
from __future__ import annotations

import logging
import os
import sqlite3
import threading
import time
from pathlib import Path
from typing import Protocol

logger = logging.getLogger("ai_agent_7h.rate_limit")


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
    """Process-safe rate limiter backed by SQLite (shared across local workers)."""

    def __init__(self, db_path: str | Path | None = None) -> None:
        base = Path(os.getenv("OUTPUT_DIR", "/tmp/generated"))
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

class RateLimiter:
    """Facade: prefers Redis, falls back to SQLite without changing callers."""

    def __init__(self) -> None:
        self._backend: RateLimiterBackend = self._select_backend()

    @staticmethod
    def _select_backend() -> RateLimiterBackend:
        url = (os.getenv("REDIS_URL") or "").strip()
        if url:
            try:
                backend = RedisRateLimiter(url)
                logger.info("rate_limit backend=redis url_host=%s", url.split("@")[-1][:64])
                return backend
            except Exception as exc:
                logger.warning(
                    "rate_limit redis unavailable (%s); falling back to sqlite", exc
                )
        logger.info("rate_limit backend=sqlite")
        return SqliteRateLimiter()

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
