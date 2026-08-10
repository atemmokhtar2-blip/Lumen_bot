"""Process-safe rate limiter backed by SQLite (shared across workers)."""
from __future__ import annotations

import os
import sqlite3
import threading
import time
from pathlib import Path


class RateLimiter:
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
        """Return True and record a hit if under limit (atomic)."""
        if limit <= 0:
            return True
        now = time.time()
        cutoff = now - window_sec
        bucket = str(key)
        conn = self._conn()
        with conn:  # transaction
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
        """Seconds until oldest hit in window expires (0 if under limit)."""
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


_LIMITER: RateLimiter | None = None


def get_rate_limiter() -> RateLimiter:
    global _LIMITER
    if _LIMITER is None:
        _LIMITER = RateLimiter()
    return _LIMITER
