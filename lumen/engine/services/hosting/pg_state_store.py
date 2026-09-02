"""PostgreSQL-backed hosting instance state (optional).

Activated when DATABASE_URL / TBE_DATABASE_URL is set to a postgres:// URI.
Falls back is handled by factory in state_store.get_state_store().
"""
from __future__ import annotations

import json
import logging
import os
import time
from typing import Any
from urllib.parse import urlparse

logger = logging.getLogger("tbe.hosting.pg_state")

_SCHEMA = """
CREATE TABLE IF NOT EXISTS tbe_host_instances (
  instance_id TEXT PRIMARY KEY,
  user_id BIGINT NOT NULL,
  project_path TEXT NOT NULL DEFAULT '',
  entry_point TEXT NOT NULL DEFAULT '',
  bot_username TEXT NOT NULL DEFAULT '',
  status TEXT NOT NULL DEFAULT 'stopped',
  deployment_id TEXT NOT NULL DEFAULT '',
  sandbox_backend TEXT NOT NULL DEFAULT '',
  pid BIGINT,
  started_at DOUBLE PRECISION NOT NULL DEFAULT 0,
  last_error TEXT NOT NULL DEFAULT '',
  last_diagnosis TEXT NOT NULL DEFAULT '',
  token_fp TEXT NOT NULL DEFAULT '',
  public_base_url TEXT NOT NULL DEFAULT '',
  webhook_public_url TEXT NOT NULL DEFAULT '',
  internal_port BIGINT NOT NULL DEFAULT 0,
  platform TEXT NOT NULL DEFAULT 'telegram',
  cpu_quota DOUBLE PRECISION NOT NULL DEFAULT 0.5,
  memory_mb BIGINT NOT NULL DEFAULT 256,
  version_ref TEXT NOT NULL DEFAULT '',
  last_health_at DOUBLE PRECISION NOT NULL DEFAULT 0,
  updated_at DOUBLE PRECISION NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_tbe_host_user ON tbe_host_instances(user_id);
CREATE INDEX IF NOT EXISTS idx_tbe_host_status ON tbe_host_instances(status);
"""


def _dsn() -> str:
    return (os.getenv("TBE_DATABASE_URL") or os.getenv("DATABASE_URL") or "").strip()


def is_postgres_url(url: str | None = None) -> bool:
    u = (url or _dsn()).lower()
    return u.startswith("postgres://") or u.startswith("postgresql://")


class PgHostStateStore:
    def __init__(self, dsn: str | None = None) -> None:
        self.dsn = dsn or _dsn()
        if not is_postgres_url(self.dsn):
            raise ValueError("not_a_postgres_dsn")
        self._ensure_schema()

    def _connect(self):
        try:
            import psycopg
        except ImportError:
            import psycopg2 as psycopg  # type: ignore
        return psycopg.connect(self.dsn)

    def _ensure_schema(self) -> None:
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(_SCHEMA)
                try:
                    cur.execute("ALTER TABLE tbe_host_instances ADD COLUMN IF NOT EXISTS sandbox_backend TEXT NOT NULL DEFAULT ''")
                except Exception:
                    pass
            conn.commit()

    def _row_to_dict(self, row) -> dict[str, Any]:
        if isinstance(row, dict):
            return dict(row)
        keys = [
            "instance_id", "user_id", "project_path", "entry_point", "bot_username",
            "status", "deployment_id", "sandbox_backend", "pid", "started_at", "last_error",
            "last_diagnosis", "token_fp", "public_base_url", "webhook_public_url", "internal_port", "platform", "cpu_quota", "memory_mb", "version_ref",
            "last_health_at", "updated_at",
        ]
        return {k: row[i] for i, k in enumerate(keys)}

    def list_all(self) -> list[dict[str, Any]]:
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT instance_id, user_id, project_path, entry_point, bot_username, status, deployment_id, sandbox_backend, pid, started_at, last_error, last_diagnosis, token_fp, public_base_url, webhook_public_url, internal_port, platform, cpu_quota, memory_mb, version_ref, last_health_at, updated_at FROM tbe_host_instances")
                rows = cur.fetchall()
        return [self._row_to_dict(r) for r in rows]

    def upsert(self, inst: dict[str, Any]) -> None:
        diag = inst.get("last_diagnosis") or ""
        if not isinstance(diag, str):
            diag = json.dumps(diag, ensure_ascii=False)
        payload = {
            "instance_id": inst["instance_id"],
            "user_id": int(inst["user_id"]),
            "project_path": inst.get("project_path") or "",
            "entry_point": inst.get("entry_point") or "",
            "bot_username": inst.get("bot_username") or "",
            "status": inst.get("status") or "stopped",
            "deployment_id": inst.get("deployment_id") or "",
            "sandbox_backend": inst.get("sandbox_backend") or "",
            "pid": inst.get("pid"),
            "started_at": float(inst.get("started_at") or 0),
            "last_error": inst.get("last_error") or "",
            "last_diagnosis": diag,
            "token_fp": inst.get("token_fp") or "",
            "public_base_url": inst.get("public_base_url") or "",
            "webhook_public_url": inst.get("webhook_public_url") or "",
            "internal_port": int(inst.get("internal_port") or 0),
            "platform": inst.get("platform") or "telegram",
            "cpu_quota": float(inst.get("cpu_quota") or 0.5),
            "memory_mb": int(inst.get("memory_mb") or 256),
            "version_ref": inst.get("version_ref") or "",
            "last_health_at": float(inst.get("last_health_at") or 0),
            "updated_at": time.time(),
        }
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO tbe_host_instances (
                      instance_id, user_id, project_path, entry_point, bot_username,
                      status, deployment_id, sandbox_backend, pid, started_at, last_error, last_diagnosis,
                      token_fp, public_base_url, webhook_public_url, internal_port, platform, cpu_quota, memory_mb, version_ref, last_health_at, updated_at
                    ) VALUES (
                      %(instance_id)s, %(user_id)s, %(project_path)s, %(entry_point)s, %(bot_username)s,
                      %(status)s, %(deployment_id)s, %(sandbox_backend)s, %(pid)s, %(started_at)s, %(last_error)s, %(last_diagnosis)s,
                      %(token_fp)s, %(public_base_url)s, %(webhook_public_url)s, %(internal_port)s, %(platform)s, %(cpu_quota)s, %(memory_mb)s, %(version_ref)s, %(last_health_at)s, %(updated_at)s
                    )
                    ON CONFLICT (instance_id) DO UPDATE SET
                      user_id=EXCLUDED.user_id,
                      project_path=EXCLUDED.project_path,
                      entry_point=EXCLUDED.entry_point,
                      bot_username=EXCLUDED.bot_username,
                      status=EXCLUDED.status,
                      deployment_id=EXCLUDED.deployment_id,
                      sandbox_backend=EXCLUDED.sandbox_backend,
                      pid=EXCLUDED.pid,
                      started_at=EXCLUDED.started_at,
                      last_error=EXCLUDED.last_error,
                      last_diagnosis=EXCLUDED.last_diagnosis,
                      token_fp=EXCLUDED.token_fp,
                      public_base_url=EXCLUDED.public_base_url,
                      webhook_public_url=EXCLUDED.webhook_public_url,
                      internal_port=EXCLUDED.internal_port,
                      platform=EXCLUDED.platform,
                      cpu_quota=EXCLUDED.cpu_quota,
                      memory_mb=EXCLUDED.memory_mb,
                      version_ref=EXCLUDED.version_ref,
                      last_health_at=EXCLUDED.last_health_at,
                      updated_at=EXCLUDED.updated_at
                    """,
                    payload,
                )
            conn.commit()


    def delete(self, instance_id: str) -> None:
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM tbe_host_instances WHERE instance_id = %s", (instance_id,))
            conn.commit()

    def running_for_user_or_token(
        self, *, user_id: int, project_path: str, token_fp: str
    ) -> list[dict[str, Any]]:
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT instance_id, user_id, project_path, entry_point, bot_username,
                           status, deployment_id, sandbox_backend, pid, started_at, last_error, last_diagnosis,
                           token_fp, updated_at
                    FROM tbe_host_instances
                    WHERE status = 'running'
                      AND user_id = %s
                      AND (project_path = %s OR (token_fp != '' AND token_fp = %s))
                    """,
                    (int(user_id), project_path, token_fp or ""),
                )
                rows = cur.fetchall()
        return [self._row_to_dict(r) for r in rows]
