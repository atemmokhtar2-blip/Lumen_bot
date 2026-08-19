"""Persisted deployment registry — multi-node safe.

Production: PostgreSQL only (DATABASE_URL) — fail-closed.
Dev: SQLite under OUTPUT_DIR/hosting allowed when ENVIRONMENT=dev|local|test.
"""
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
import logging
import os
import socket
import sqlite3
import time
from pathlib import Path
from typing import Any, Optional, Protocol

logger = logging.getLogger("tbe.deployment_registry")

_SCHEMA_SQLITE = """
CREATE TABLE IF NOT EXISTS deployments (
  deployment_id TEXT PRIMARY KEY,
  user_id INTEGER NOT NULL DEFAULT 0,
  container_name TEXT NOT NULL DEFAULT '',
  container_id TEXT NOT NULL DEFAULT '',
  image_tag TEXT NOT NULL DEFAULT '',
  project_path TEXT NOT NULL DEFAULT '',
  node_id TEXT NOT NULL DEFAULT '',
  status TEXT NOT NULL DEFAULT 'unknown',
  created_at REAL NOT NULL DEFAULT 0,
  updated_at REAL NOT NULL DEFAULT 0,
  meta_json TEXT NOT NULL DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS idx_dep_user ON deployments(user_id);
CREATE INDEX IF NOT EXISTS idx_dep_status ON deployments(status);
"""

_SCHEMA_PG = """
CREATE TABLE IF NOT EXISTS deployments (
  deployment_id TEXT PRIMARY KEY,
  user_id BIGINT NOT NULL DEFAULT 0,
  container_name TEXT NOT NULL DEFAULT '',
  container_id TEXT NOT NULL DEFAULT '',
  image_tag TEXT NOT NULL DEFAULT '',
  project_path TEXT NOT NULL DEFAULT '',
  node_id TEXT NOT NULL DEFAULT '',
  status TEXT NOT NULL DEFAULT 'unknown',
  created_at DOUBLE PRECISION NOT NULL DEFAULT 0,
  updated_at DOUBLE PRECISION NOT NULL DEFAULT 0,
  meta_json JSONB NOT NULL DEFAULT '{}'::jsonb
);
CREATE INDEX IF NOT EXISTS idx_dep_user ON deployments(user_id);
CREATE INDEX IF NOT EXISTS idx_dep_status ON deployments(status);
"""


def node_id() -> str:
    return (os.environ.get("TBE_NODE_ID") or socket.gethostname() or "node").strip()[:64]


def _is_dev() -> bool:
    env = (os.getenv("ENVIRONMENT") or os.getenv("TBE_ENV") or "").strip().lower()
    return env in {"dev", "development", "local", "test"}


def _database_url() -> str:
    return (
        (os.getenv("DATABASE_URL") or "")
        or (os.getenv("POSTGRES_URL") or "")
        or (os.getenv("POSTGRESQL_URL") or "")
    ).strip()


class DeploymentRegistry(Protocol):
    def upsert(self, record: dict[str, Any]) -> None: ...
    def get(self, deployment_id: str) -> Optional[dict[str, Any]]: ...
    def mark_status(self, deployment_id: str, status: str) -> None: ...
    def by_project(self, project_path: str) -> list[dict[str, Any]]: ...


class SqliteDeploymentRegistry:
    """Dev-only local registry."""

    def __init__(self, db_path: str | Path | None = None) -> None:
        if not _is_dev():
            raise RuntimeError(
                "SqliteDeploymentRegistry is forbidden outside ENVIRONMENT=dev. "
                "Set DATABASE_URL for PostgreSQL deployment registry."
            )
        base = Path(os.environ.get("OUTPUT_DIR") or _cm_default_output_dir()) / "hosting"
        base.mkdir(parents=True, exist_ok=True)
        self.path = Path(db_path or (base / "deployments.sqlite3"))
        self._init()

    def _conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.path), timeout=30, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        return conn

    def _init(self) -> None:
        with self._conn() as c:
            c.executescript(_SCHEMA_SQLITE)

    def upsert(self, record: dict[str, Any]) -> None:
        rec = dict(record)
        rec.setdefault("updated_at", time.time())
        rec.setdefault("created_at", time.time())
        rec.setdefault("node_id", node_id())
        meta = rec.get("meta_json") or {}
        if not isinstance(meta, str):
            meta = json.dumps(meta, ensure_ascii=False)
        with self._conn() as c:
            c.execute(
                """
                INSERT INTO deployments (
                  deployment_id, user_id, container_name, container_id, image_tag,
                  project_path, node_id, status, created_at, updated_at, meta_json
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(deployment_id) DO UPDATE SET
                  user_id=excluded.user_id,
                  container_name=excluded.container_name,
                  container_id=excluded.container_id,
                  image_tag=excluded.image_tag,
                  project_path=excluded.project_path,
                  node_id=excluded.node_id,
                  status=excluded.status,
                  updated_at=excluded.updated_at,
                  meta_json=excluded.meta_json
                """,
                (
                    rec["deployment_id"],
                    int(rec.get("user_id") or 0),
                    rec.get("container_name") or "",
                    rec.get("container_id") or "",
                    rec.get("image_tag") or "",
                    rec.get("project_path") or "",
                    rec.get("node_id") or node_id(),
                    rec.get("status") or "unknown",
                    float(rec.get("created_at") or time.time()),
                    float(rec.get("updated_at") or time.time()),
                    meta,
                ),
            )

    def get(self, deployment_id: str) -> Optional[dict[str, Any]]:
        with self._conn() as c:
            row = c.execute(
                "SELECT * FROM deployments WHERE deployment_id=?", (deployment_id,)
            ).fetchone()
        return dict(row) if row else None

    def mark_status(self, deployment_id: str, status: str) -> None:
        with self._conn() as c:
            c.execute(
                "UPDATE deployments SET status=?, updated_at=? WHERE deployment_id=?",
                (status, time.time(), deployment_id),
            )

    def by_project(self, project_path: str) -> list[dict[str, Any]]:
        with self._conn() as c:
            rows = c.execute(
                "SELECT * FROM deployments WHERE project_path=? ORDER BY updated_at DESC",
                (project_path,),
            ).fetchall()
        return [dict(r) for r in rows]


class PostgresDeploymentRegistry:
    """Production multi-node registry on PostgreSQL."""

    def __init__(self, dsn: str | None = None) -> None:
        try:
            import psycopg
            from psycopg.rows import dict_row
        except ImportError as exc:
            raise RuntimeError(
                "psycopg required for PostgresDeploymentRegistry. pip install 'psycopg[binary]'"
            ) from exc
        self.dsn = (dsn or _database_url()).strip()
        if not self.dsn:
            raise ValueError("DATABASE_URL required for PostgresDeploymentRegistry")
        self._psycopg = psycopg
        self._dict_row = dict_row
        self._ensure_schema()
        logger.info("PostgresDeploymentRegistry ready")

    def _conn(self):
        return self._psycopg.connect(self.dsn, row_factory=self._dict_row)

    def _ensure_schema(self) -> None:
        with self._conn() as conn:
            conn.execute(_SCHEMA_PG)
            conn.commit()

    def upsert(self, record: dict[str, Any]) -> None:
        rec = dict(record)
        rec.setdefault("updated_at", time.time())
        rec.setdefault("created_at", time.time())
        rec.setdefault("node_id", node_id())
        meta = rec.get("meta_json") or {}
        if isinstance(meta, str):
            try:
                meta = json.loads(meta)
            except Exception:
                meta = {}
        with self._conn() as conn:
            conn.execute(
                """
                INSERT INTO deployments (
                  deployment_id, user_id, container_name, container_id, image_tag,
                  project_path, node_id, status, created_at, updated_at, meta_json
                ) VALUES (
                  %(deployment_id)s, %(user_id)s, %(container_name)s, %(container_id)s,
                  %(image_tag)s, %(project_path)s, %(node_id)s, %(status)s,
                  %(created_at)s, %(updated_at)s, %(meta_json)s::jsonb
                )
                ON CONFLICT (deployment_id) DO UPDATE SET
                  user_id = EXCLUDED.user_id,
                  container_name = EXCLUDED.container_name,
                  container_id = EXCLUDED.container_id,
                  image_tag = EXCLUDED.image_tag,
                  project_path = EXCLUDED.project_path,
                  node_id = EXCLUDED.node_id,
                  status = EXCLUDED.status,
                  updated_at = EXCLUDED.updated_at,
                  meta_json = EXCLUDED.meta_json
                """,
                {
                    "deployment_id": rec["deployment_id"],
                    "user_id": int(rec.get("user_id") or 0),
                    "container_name": rec.get("container_name") or "",
                    "container_id": rec.get("container_id") or "",
                    "image_tag": rec.get("image_tag") or "",
                    "project_path": rec.get("project_path") or "",
                    "node_id": rec.get("node_id") or node_id(),
                    "status": rec.get("status") or "unknown",
                    "created_at": float(rec.get("created_at") or time.time()),
                    "updated_at": float(rec.get("updated_at") or time.time()),
                    "meta_json": json.dumps(meta if isinstance(meta, dict) else {}),
                },
            )
            conn.commit()

    def get(self, deployment_id: str) -> Optional[dict[str, Any]]:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT * FROM deployments WHERE deployment_id=%s",
                (deployment_id,),
            ).fetchone()
        if not row:
            return None
        out = dict(row)
        if isinstance(out.get("meta_json"), dict):
            out["meta_json"] = json.dumps(out["meta_json"], ensure_ascii=False)
        return out

    def mark_status(self, deployment_id: str, status: str) -> None:
        with self._conn() as conn:
            conn.execute(
                "UPDATE deployments SET status=%s, updated_at=%s WHERE deployment_id=%s",
                (status, time.time(), deployment_id),
            )
            conn.commit()

    def by_project(self, project_path: str) -> list[dict[str, Any]]:
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT * FROM deployments WHERE project_path=%s ORDER BY updated_at DESC",
                (project_path,),
            ).fetchall()
        out = []
        for r in rows:
            d = dict(r)
            if isinstance(d.get("meta_json"), dict):
                d["meta_json"] = json.dumps(d["meta_json"], ensure_ascii=False)
            out.append(d)
        return out


# Back-compat alias used by older imports expecting class DeploymentRegistry
DeploymentRegistry = SqliteDeploymentRegistry  # type: ignore[misc,assignment]


_REGISTRY: Any = None


def get_deployment_registry():
    """Production → Postgres. Dev without DATABASE_URL → SQLite."""
    global _REGISTRY
    if _REGISTRY is not None:
        return _REGISTRY
    pg = _database_url()
    if pg:
        _REGISTRY = PostgresDeploymentRegistry(pg)
        return _REGISTRY
    if _is_dev():
        logger.warning("DEV ONLY: SQLite deployment registry. Set DATABASE_URL for production.")
        _REGISTRY = SqliteDeploymentRegistry()
        return _REGISTRY
    raise RuntimeError(
        "DATABASE_URL is required for deployment registry outside ENVIRONMENT=dev. "
        "SQLite deployments.sqlite3 is not multi-node safe."
    )
