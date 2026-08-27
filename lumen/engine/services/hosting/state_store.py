"""SQLite-backed hosting instance registry (atomic, multi-thread safe).

Replaces the JSON file as the source of truth so start/stop mutations
happen under BEGIN IMMEDIATE transactions (real atomicity, not just
advisory locks around a JSON rewrite).
"""
from __future__ import annotations

import os

import json
import sqlite3
import threading
import time
from dataclasses import asdict, fields
from pathlib import Path
from typing import Any, Iterable

_SCHEMA = """
CREATE TABLE IF NOT EXISTS instances (
    instance_id TEXT PRIMARY KEY,
    user_id INTEGER NOT NULL,
    project_path TEXT NOT NULL,
    entry_point TEXT DEFAULT '',
    bot_username TEXT DEFAULT '',
    status TEXT NOT NULL,
    deployment_id TEXT DEFAULT '',
    sandbox_backend TEXT DEFAULT '',
    pid INTEGER,
    started_at REAL DEFAULT 0,
    last_error TEXT DEFAULT '',
    last_diagnosis TEXT DEFAULT '{}',
    token_fp TEXT DEFAULT '',
    updated_at REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_instances_user ON instances(user_id);
CREATE INDEX IF NOT EXISTS idx_instances_token ON instances(token_fp);
"""


class HostingStateStore:
    """Process-shared SQLite store — **dev only**. Production must use PgHostStateStore."""

    def __init__(self, db_path: Path) -> None:
        env = (os.getenv("ENVIRONMENT") or os.getenv("TBE_ENV") or "").strip().lower()
        if env not in {"dev", "development", "local", "test"}:
            raise RuntimeError(
                "SQLite HostingStateStore is forbidden outside ENVIRONMENT=dev. "
                "Set DATABASE_URL (postgresql://...) for PgHostStateStore."
            )
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._local = threading.local()
        self._init_db()

    def _conn(self) -> sqlite3.Connection:
        conn = getattr(self._local, "conn", None)
        if conn is None:
            conn = sqlite3.connect(
                str(self.db_path),
                timeout=30.0,
                isolation_level=None,  # manual transactions
                check_same_thread=False,
            )
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA synchronous=NORMAL")
            conn.execute("PRAGMA busy_timeout=30000")
            self._local.conn = conn
        return conn

    def _init_db(self) -> None:
        conn = self._conn()
        conn.executescript(_SCHEMA)
        try:
            conn.execute("ALTER TABLE instances ADD COLUMN sandbox_backend TEXT DEFAULT ''")
        except Exception:
            pass

    def _row_to_dict(self, row: sqlite3.Row) -> dict[str, Any]:
        d = dict(row)
        try:
            d["last_diagnosis"] = json.loads(d.get("last_diagnosis") or "{}")
        except Exception:
            d["last_diagnosis"] = {}
        return d

    def list_all(self) -> list[dict[str, Any]]:
        conn = self._conn()
        rows = conn.execute("SELECT * FROM instances").fetchall()
        return [self._row_to_dict(r) for r in rows]

    def list_for_user(self, user_id: int) -> list[dict[str, Any]]:
        conn = self._conn()
        rows = conn.execute(
            "SELECT * FROM instances WHERE user_id = ?",
            (int(user_id),),
        ).fetchall()
        return [self._row_to_dict(r) for r in rows]

    def get(self, instance_id: str) -> dict[str, Any] | None:
        conn = self._conn()
        row = conn.execute(
            "SELECT * FROM instances WHERE instance_id = ?",
            (instance_id,),
        ).fetchone()
        return self._row_to_dict(row) if row else None

    def upsert(self, inst: dict[str, Any]) -> None:
        conn = self._conn()
        conn.execute("BEGIN IMMEDIATE")
        try:
            diag = inst.get("last_diagnosis") or {}
            if not isinstance(diag, str):
                diag = json.dumps(diag, ensure_ascii=False)
            conn.execute(
                """
                INSERT INTO instances (
                    instance_id, user_id, project_path, entry_point, bot_username,
                    status, deployment_id, pid, started_at, last_error,
                    last_diagnosis, token_fp, updated_at
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(instance_id) DO UPDATE SET
                    user_id=excluded.user_id,
                    project_path=excluded.project_path,
                    entry_point=excluded.entry_point,
                    bot_username=excluded.bot_username,
                    status=excluded.status,
                    deployment_id=excluded.deployment_id,
                    pid=excluded.pid,
                    started_at=excluded.started_at,
                    last_error=excluded.last_error,
                    last_diagnosis=excluded.last_diagnosis,
                    token_fp=excluded.token_fp,
                    updated_at=excluded.updated_at
                """,
                (
                    inst["instance_id"],
                    int(inst["user_id"]),
                    inst.get("project_path") or "",
                    inst.get("entry_point") or "",
                    inst.get("bot_username") or "",
                    inst.get("status") or "stopped",
                    inst.get("deployment_id") or "",
                    inst.get("sandbox_backend") or "",
                    inst.get("pid"),
                    float(inst.get("started_at") or 0),
                    inst.get("last_error") or "",
                    diag,
                    inst.get("token_fp") or "",
                    time.time(),
                ),
            )
            conn.execute("COMMIT")
        except Exception:
            conn.execute("ROLLBACK")
            raise

    def delete(self, instance_id: str) -> None:
        conn = self._conn()
        conn.execute("BEGIN IMMEDIATE")
        try:
            conn.execute("DELETE FROM instances WHERE instance_id = ?", (instance_id,))
            conn.execute("COMMIT")
        except Exception:
            conn.execute("ROLLBACK")
            raise

    def running_for_user_or_token(
        self, *, user_id: int, project_path: str, token_fp: str
    ) -> list[dict[str, Any]]:
        """Atomically list conflicting running instances for stop-before-start."""
        conn = self._conn()
        conn.execute("BEGIN IMMEDIATE")
        try:
            rows = conn.execute(
                """
                SELECT * FROM instances
                WHERE status = 'running'
                  AND user_id = ?
                  AND (project_path = ? OR (token_fp != '' AND token_fp = ?))
                """,
                (int(user_id), project_path, token_fp or ""),
            ).fetchall()
            result = [self._row_to_dict(r) for r in rows]
            conn.execute("COMMIT")
            return result
        except Exception:
            conn.execute("ROLLBACK")
            raise


def get_host_state_store(sqlite_path: str | Path | None = None):
    """Production: Postgres only (fail-closed). Dev: SQLite allowed."""
    env = (os.getenv("ENVIRONMENT") or os.getenv("TBE_ENV") or "production").strip().lower()
    is_dev = env in {"dev", "development", "local", "test"}
    try:
        from lumen.engine.services.hosting.pg_state_store import (
            PgHostStateStore,
            is_postgres_url,
        )
        if is_postgres_url():
            return PgHostStateStore()
    except Exception as exc:
        if not is_dev:
            raise RuntimeError(
                f"Postgres host state store required in production: {type(exc).__name__}: {exc}"
            ) from exc
        import logging
        logging.getLogger("tbe.hosting").warning("postgres state unavailable in dev: %s", exc)
    if not is_dev:
        raise RuntimeError(
            "DATABASE_URL (postgresql://...) is required for host state outside ENVIRONMENT=dev. "
            "SQLite instances.sqlite3 is not multi-node safe."
        )
    path = Path(sqlite_path) if sqlite_path else None
    if path is None:
        raise TypeError("sqlite_path required when not using Postgres")
    import logging
    logging.getLogger("tbe.hosting").warning("DEV ONLY: SQLite host state store")
    return HostingStateStore(path)
