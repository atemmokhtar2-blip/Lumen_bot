"""SQLite-backed user session persistence (survives restarts, multi-worker safe)."""
from __future__ import annotations

def _cm_default_output_dir() -> str:
    try:
        from b2b_platform.paths import default_output_dir
        return default_output_dir()
    except Exception:
        from pathlib import Path as _P
        p = _P.home() / '.capability_maestro'
        p.mkdir(parents=True, exist_ok=True)
        return str(p)


import json
import os
import sqlite3
import threading
import time
from pathlib import Path
from typing import Any


class SessionStore:
    def __init__(self, path: str | Path | None = None) -> None:
        root = Path(os.getenv("OUTPUT_DIR") or _cm_default_output_dir())
        root.mkdir(parents=True, exist_ok=True)
        self.path = Path(path or root / "sessions.sqlite3")
        self._lock = threading.Lock()
        self._init()

    def _conn(self) -> sqlite3.Connection:
        c = sqlite3.connect(str(self.path), timeout=30, check_same_thread=False)
        c.row_factory = sqlite3.Row
        c.execute("PRAGMA journal_mode=WAL")
        return c

    def _init(self) -> None:
        with self._lock:
            with self._conn() as conn:
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS sessions (
                        user_id INTEGER PRIMARY KEY,
                        data_json TEXT NOT NULL DEFAULT '{}',
                        updated_at REAL NOT NULL
                    )
                    """
                )
                conn.commit()

    def load(self, user_id: int) -> dict[str, Any]:
        with self._lock:
            with self._conn() as conn:
                row = conn.execute(
                    "SELECT data_json FROM sessions WHERE user_id=?",
                    (int(user_id),),
                ).fetchone()
        if not row:
            return {}
        try:
            data = json.loads(row["data_json"] or "{}")
            return data if isinstance(data, dict) else {}
        except Exception:
            return {}

    def save(self, user_id: int, data: dict[str, Any]) -> None:
        # Only persist durable keys — avoid huge blobs
        keep = {
            k: data[k]
            for k in (
                "pending_run",
                "pending_live_run",
                "pending_deploy",
                "pending_host",
                "pending_clone_auth",
                "active_repo",
                "chat_history",
                "last_bot_request",
                "pending_chat_action",
                "translated_preferred_keys",
                "translated_source",
                "last_project_path",
                "active_bot_path",
            )
            if k in data and data[k] is not None
        }
        payload = json.dumps(keep, ensure_ascii=False, default=str)
        with self._lock:
            with self._conn() as conn:
                conn.execute(
                    """
                    INSERT INTO sessions(user_id, data_json, updated_at)
                    VALUES(?,?,?)
                    ON CONFLICT(user_id) DO UPDATE SET
                        data_json=excluded.data_json,
                        updated_at=excluded.updated_at
                    """,
                    (int(user_id), payload, time.time()),
                )
                conn.commit()

    def clear(self, user_id: int) -> None:
        with self._lock:
            with self._conn() as conn:
                conn.execute("DELETE FROM sessions WHERE user_id=?", (int(user_id),))
                conn.commit()


_store: SessionStore | None = None


def get_session_store() -> SessionStore:
    global _store
    if _store is None:
        _store = SessionStore()
    return _store


__all__ = ["SessionStore", "get_session_store"]
