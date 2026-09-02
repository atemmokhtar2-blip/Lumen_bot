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
    public_base_url TEXT DEFAULT '',
    webhook_public_url TEXT DEFAULT '',
    internal_port INTEGER DEFAULT 0,
    platform TEXT DEFAULT 'telegram',
    cpu_quota REAL DEFAULT 0.5,
    memory_mb INTEGER DEFAULT 256,
    version_ref TEXT DEFAULT '',
    last_health_at REAL DEFAULT 0,
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
        for col, decl in (
            ("public_base_url", "TEXT DEFAULT ''"),
            ("webhook_public_url", "TEXT DEFAULT ''"),
            ("internal_port", "INTEGER DEFAULT 0"),
            ("platform", "TEXT DEFAULT 'telegram'"),
            ("cpu_quota", "REAL DEFAULT 0.5"),
            ("memory_mb", "INTEGER DEFAULT 256"),
            ("version_ref", "TEXT DEFAULT ''"),
            ("last_health_at", "REAL DEFAULT 0"),
        ):
            try:
                conn.execute(f"ALTER TABLE instances ADD COLUMN {col} {decl}")
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
                    status, deployment_id, sandbox_backend, pid, started_at, last_error,
                    last_diagnosis, token_fp, public_base_url, webhook_public_url, internal_port, platform, cpu_quota, memory_mb, version_ref, last_health_at,
                    updated_at
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(instance_id) DO UPDATE SET
                    user_id=excluded.user_id,
                    project_path=excluded.project_path,
                    entry_point=excluded.entry_point,
                    bot_username=excluded.bot_username,
                    status=excluded.status,
                    deployment_id=excluded.deployment_id,
                    sandbox_backend=excluded.sandbox_backend,
                    pid=excluded.pid,
                    started_at=excluded.started_at,
                    last_error=excluded.last_error,
                    last_diagnosis=excluded.last_diagnosis,
                    token_fp=excluded.token_fp,
                    public_base_url=excluded.public_base_url,
                    webhook_public_url=excluded.webhook_public_url,
                    internal_port=excluded.internal_port,
                    platform=excluded.platform,
                    cpu_quota=excluded.cpu_quota,
                    memory_mb=excluded.memory_mb,
                    version_ref=excluded.version_ref,
                    last_health_at=excluded.last_health_at,
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
                    inst.get("public_base_url") or "",
                    inst.get("webhook_public_url") or "",
                    int(inst.get("internal_port") or 0),
                    inst.get("platform") or "telegram",
                    float(inst.get("cpu_quota") or 0.5),
                    int(inst.get("memory_mb") or 256),
                    inst.get("version_ref") or "",
                    float(inst.get("last_health_at") or 0),
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


def _is_scale_mode() -> bool:
    """True when TBE_SCALE_MODE indicates multi-node worker deployment."""
    return (os.getenv("TBE_SCALE_MODE") or "").strip().lower() in {"1", "true", "yes", "on"}


def _shared_fs_available() -> bool:
    """Heuristic: is the SQLite path on a shared/network filesystem?

    On multi-node, SQLite MUST be on a shared volume (NFS, EFS, etc.) for
    WAL to work across nodes. We check common network-FS indicators.
    """
    # If DATABASE_URL points to postgres, we wouldn't be here — this is
    # only called in the SQLite fallback path.
    import stat
    try:
        out_dir = Path(os.getenv("OUTPUT_DIR") or ".")
        if not out_dir.exists():
            return False
        st = out_dir.stat()
        # NFS (0x6969), CIFS/SMB (0x0000517B), overlay/fuse, etc.
        # Major device magic numbers for network filesystems.
        network_fs_magic = {
            0x6969,      # NFS
            0x65735546,  # FUSE
            0xFF534D42,  # CIFS/SMB1
            0xFE534D42,  # CIFS/SMB2
        }
        if st.st_dev in network_fs_magic:
            return True
    except (OSError, ValueError):
        pass
    return False


def get_host_state_store(sqlite_path: str | Path | None = None):
    """Production: Postgres only (fail-closed). Dev: SQLite allowed.

    Multi-node safety (TBE_SCALE_MODE=1):
      - SQLite on local disk is NOT safe for concurrent multi-node writes.
      - If scale mode is on and Postgres is not configured, we fail-closed
        unless the SQLite path is on a shared/network filesystem.
    """
    env = (os.getenv("ENVIRONMENT") or os.getenv("TBE_ENV") or "production").strip().lower()
    is_dev = env in {"dev", "development", "local", "test"}

    # Try Postgres first (the only truly multi-node-safe backend).
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

    # --- Dev-only SQLite path below ---

    # Multi-node guard: fail-closed if scale mode is on without shared FS.
    if _is_scale_mode() and not _shared_fs_available():
        raise RuntimeError(
            "TBE_SCALE_MODE=1 (multi-node) requires a shared filesystem for SQLite "
            "or DATABASE_URL=postgresql://... — local-disk SQLite will corrupt under "
            "concurrent multi-node writes. Either: (1) set DATABASE_URL to Postgres, "
            "or (2) mount OUTPUT_DIR on NFS/EFS, or (3) disable TBE_SCALE_MODE for "
            "single-node dev."
        )

    path = Path(sqlite_path) if sqlite_path else None
    if path is None:
        raise TypeError("sqlite_path required when not using Postgres")
    import logging
    logging.getLogger("tbe.hosting").warning(
        "DEV ONLY: SQLite host state store (WAL mode enabled%s)",
        " + multi-node shared-FS" if _is_scale_mode() else "",
    )
    return HostingStateStore(path)
