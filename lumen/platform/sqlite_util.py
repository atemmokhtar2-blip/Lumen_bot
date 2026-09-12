"""Shared SQLite connection helpers (WAL + Row factory)."""
from __future__ import annotations

import sqlite3
from pathlib import Path


def open_wal_connection(path: str | Path, *, timeout: float = 30.0) -> sqlite3.Connection:
    c = sqlite3.connect(str(path), timeout=timeout, check_same_thread=False)
    c.row_factory = sqlite3.Row
    try:
        c.execute("PRAGMA journal_mode=WAL")
    except Exception:
        pass
    return c


__all__ = ["open_wal_connection"]
