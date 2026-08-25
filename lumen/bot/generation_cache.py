"""Short-TTL cache for identical generation requests (duplicate sends)."""
from __future__ import annotations

def _cm_default_output_dir() -> str:
    try:
        from lumen.platform.paths import default_output_dir
        return default_output_dir()
    except Exception:
        from pathlib import Path as _P
        p = _P.home() / '.lumen'
        p.mkdir(parents=True, exist_ok=True)
        return str(p)


import hashlib
import json
import os
import sqlite3
import threading
import time
from pathlib import Path
from typing import Any


class GenerationCache:
    def __init__(self, path: str | Path | None = None, ttl_sec: float = 120.0) -> None:
        root = Path(os.getenv("OUTPUT_DIR") or _cm_default_output_dir())
        root.mkdir(parents=True, exist_ok=True)
        self.path = Path(path or root / "generation_cache.sqlite3")
        self.ttl = float(os.getenv("GENERATION_CACHE_TTL") or ttl_sec)
        self._lock = threading.Lock()
        self._init()

    def _conn(self) -> sqlite3.Connection:
        c = sqlite3.connect(str(self.path), timeout=30, check_same_thread=False)
        c.execute("PRAGMA journal_mode=WAL")
        return c

    def _init(self) -> None:
        with self._lock:
            with self._conn() as conn:
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS gen_cache (
                        cache_key TEXT PRIMARY KEY,
                        result_json TEXT NOT NULL,
                        created_at REAL NOT NULL
                    )
                    """
                )
                conn.commit()

    @staticmethod
    def key_for(user_id: int, request: str) -> str:
        h = hashlib.sha256(f"{int(user_id)}\n{(request or '').strip()}".encode()).hexdigest()
        return h

    def get(self, user_id: int, request: str) -> dict[str, Any] | None:
        k = self.key_for(user_id, request)
        now = time.time()
        with self._lock:
            with self._conn() as conn:
                conn.execute("DELETE FROM gen_cache WHERE created_at < ?", (now - self.ttl,))
                row = conn.execute(
                    "SELECT result_json, created_at FROM gen_cache WHERE cache_key=?",
                    (k,),
                ).fetchone()
        if not row:
            return None
        if float(row[1]) < now - self.ttl:
            return None
        try:
            return json.loads(row[0])
        except Exception:
            return None

    def put(self, user_id: int, request: str, payload: dict[str, Any]) -> None:
        k = self.key_for(user_id, request)
        with self._lock:
            with self._conn() as conn:
                conn.execute(
                    """
                    INSERT INTO gen_cache(cache_key, result_json, created_at)
                    VALUES(?,?,?)
                    ON CONFLICT(cache_key) DO UPDATE SET
                        result_json=excluded.result_json,
                        created_at=excluded.created_at
                    """,
                    (k, json.dumps(payload, ensure_ascii=False, default=str), time.time()),
                )
                conn.commit()


_cache: GenerationCache | None = None


def get_generation_cache() -> GenerationCache:
    global _cache
    if _cache is None:
        _cache = GenerationCache()
    return _cache
