"""Persisted deployment registry — survives process restart and enables multi-node ops.

Stores container_name, image_tag, node_id, project_path keyed by deployment_id.
Backend: same Postgres as host state when available, else SQLite under OUTPUT_DIR/hosting.
"""
from __future__ import annotations

import json
import logging
import os
import socket
import sqlite3
import time
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger("tbe.deployment_registry")

_SCHEMA = """
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


def node_id() -> str:
    return (os.environ.get("TBE_NODE_ID") or socket.gethostname() or "node").strip()[:64]


class DeploymentRegistry:
    def __init__(self, db_path: str | Path | None = None) -> None:
        base = Path(os.environ.get("OUTPUT_DIR") or "/tmp/generated") / "hosting"
        base.mkdir(parents=True, exist_ok=True)
        self.path = Path(db_path or (base / "deployments.sqlite3"))
        self._init()

    def _conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.path), timeout=30, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        return conn

    def _init(self) -> None:
        with self._conn() as c:
            c.executescript(_SCHEMA)

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


_REGISTRY: DeploymentRegistry | None = None


def get_deployment_registry() -> DeploymentRegistry:
    global _REGISTRY
    if _REGISTRY is None:
        _REGISTRY = DeploymentRegistry()
    return _REGISTRY
