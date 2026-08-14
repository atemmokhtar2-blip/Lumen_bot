"""Postgres-backed deploy queue for commercial multi-node hosting."""
from __future__ import annotations

import hashlib
import json
import logging
import os
import time
import uuid
from typing import Any, Optional

from telegram_bot_engine.services.hosting.deploy_queue import DeployJob

logger = logging.getLogger("tbe.hosting.pg_queue")

_SCHEMA = """
CREATE TABLE IF NOT EXISTS tbe_deploy_jobs (
  job_id TEXT PRIMARY KEY,
  user_id BIGINT NOT NULL,
  project_path TEXT NOT NULL,
  token_fp TEXT NOT NULL DEFAULT '',
  sealed_token TEXT NOT NULL DEFAULT '',
  status TEXT NOT NULL DEFAULT 'queued',
  node_id TEXT NOT NULL DEFAULT '',
  deployment_id TEXT NOT NULL DEFAULT '',
  image_tag TEXT NOT NULL DEFAULT '',
  attempts INT NOT NULL DEFAULT 0,
  max_attempts INT NOT NULL DEFAULT 3,
  last_error TEXT NOT NULL DEFAULT '',
  created_at DOUBLE PRECISION NOT NULL,
  updated_at DOUBLE PRECISION NOT NULL,
  claimed_at DOUBLE PRECISION NOT NULL DEFAULT 0,
  heartbeat_at DOUBLE PRECISION NOT NULL DEFAULT 0,
  meta_json TEXT NOT NULL DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS idx_tbe_jobs_status ON tbe_deploy_jobs(status, created_at);
CREATE INDEX IF NOT EXISTS idx_tbe_jobs_user ON tbe_deploy_jobs(user_id);
"""


def _dsn() -> str:
    return (os.getenv("TBE_DATABASE_URL") or os.getenv("DATABASE_URL") or "").strip()


def available() -> bool:
    u = _dsn().lower()
    return u.startswith("postgres://") or u.startswith("postgresql://")


class PgDeployQueue:
    def __init__(self, dsn: str | None = None) -> None:
        self.dsn = dsn or _dsn()
        if not available():
            raise RuntimeError("postgres_dsn_required")
        self._ensure()

    def _connect(self):
        try:
            import psycopg
            return psycopg.connect(self.dsn)
        except ImportError:
            import psycopg2
            return psycopg2.connect(self.dsn)

    def _ensure(self) -> None:
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(_SCHEMA)
            conn.commit()

    def enqueue(self, *, user_id: int, project_path: str, bot_token: str, meta: dict | None = None) -> DeployJob:
        from telegram_bot_engine.services.crypto_tokens import seal_token
        token = (bot_token or "").strip()
        job_id = f"job_{uuid.uuid4().hex}"
        now = time.time()
        job = DeployJob(
            job_id=job_id,
            user_id=int(user_id),
            project_path=str(project_path),
            token_fp=hashlib.sha256(token.encode()).hexdigest()[:16] if token else "",
            sealed_token=seal_token(token),
            status="queued",
            created_at=now,
            updated_at=now,
            meta_json=json.dumps(meta or {}, ensure_ascii=False),
        )
        max_q = int((os.environ.get("TBE_MAX_QUEUED_PER_USER") or "20").strip() or "20")
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT COUNT(*) FROM tbe_deploy_jobs WHERE user_id=%s AND status IN ('queued','claimed','building')",
                    (job.user_id,),
                )
                n = int(cur.fetchone()[0])
                if n >= max_q:
                    raise RuntimeError(f"user_queue_full:{max_q}")
                cur.execute(
                    """
                    INSERT INTO tbe_deploy_jobs (
                      job_id, user_id, project_path, token_fp, sealed_token, status,
                      node_id, deployment_id, image_tag, attempts, max_attempts,
                      last_error, created_at, updated_at, claimed_at, heartbeat_at, meta_json
                    ) VALUES (
                      %s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s
                    )
                    """,
                    (
                        job.job_id, job.user_id, job.project_path, job.token_fp, job.sealed_token,
                        job.status, "", "", "", 0, job.max_attempts, "", job.created_at,
                        job.updated_at, 0.0, 0.0, job.meta_json,
                    ),
                )
            conn.commit()
        return job

    def claim_next(self, node_id: str) -> Optional[DeployJob]:
        now = time.time()
        with self._connect() as conn:
            with conn.cursor() as cur:
                # reclaim stale claimed/building jobs (worker died)
                stale = float(os.environ.get("TBE_JOB_STALE_SECONDS") or 600)
                cur.execute(
                    """
                    UPDATE tbe_deploy_jobs SET status='queued', node_id='', updated_at=%s
                    WHERE status IN ('claimed','building') AND heartbeat_at > 0 AND heartbeat_at < %s
                    """,
                    (now, now - stale),
                )
                cur.execute(
                    """
                    SELECT job_id FROM tbe_deploy_jobs
                    WHERE status='queued' ORDER BY created_at ASC LIMIT 1
                    FOR UPDATE SKIP LOCKED
                    """
                )
                row = cur.fetchone()
                if not row:
                    conn.commit()
                    return None
                job_id = row[0]
                cur.execute(
                    """
                    UPDATE tbe_deploy_jobs
                    SET status='claimed', node_id=%s, claimed_at=%s, updated_at=%s,
                        heartbeat_at=%s, attempts=attempts+1
                    WHERE job_id=%s AND status='queued'
                    """,
                    (node_id, now, now, now, job_id),
                )
            conn.commit()
        return self.get(job_id)

    def get(self, job_id: str) -> Optional[DeployJob]:
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT * FROM tbe_deploy_jobs WHERE job_id=%s", (job_id,))
                row = cur.fetchone()
                if not row:
                    return None
                cols = [d[0] for d in cur.description]
        data = dict(zip(cols, row))
        fields = DeployJob.__dataclass_fields__
        payload = {}
        for k in fields:
            if k in data:
                payload[k] = data[k]
        return DeployJob(**payload)

    def update(self, job_id: str, **fields: Any) -> None:
        allowed = {
            "status", "node_id", "deployment_id", "image_tag", "last_error",
            "attempts", "updated_at", "claimed_at", "sealed_token", "heartbeat_at",
        }
        fields = {k: v for k, v in fields.items() if k in allowed}
        fields["updated_at"] = time.time()
        if not fields:
            return
        sets = ", ".join(f"{k}=%s" for k in fields)
        vals = list(fields.values()) + [job_id]
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(f"UPDATE tbe_deploy_jobs SET {sets} WHERE job_id=%s", vals)
            conn.commit()

    def heartbeat(self, job_id: str) -> None:
        self.update(job_id, heartbeat_at=time.time())

    def mark_running(self, job_id: str, *, deployment_id: str, image_tag: str) -> None:
        self.update(
            job_id,
            status="running",
            deployment_id=deployment_id,
            image_tag=image_tag,
            sealed_token="",
            last_error="",
            heartbeat_at=time.time(),
        )

    def mark_failed(self, job_id: str, error: str) -> None:
        job = self.get(job_id)
        if not job:
            return
        if job.attempts >= job.max_attempts:
            self.update(job_id, status="failed", last_error=(error or "")[:500], sealed_token="")
        else:
            self.update(job_id, status="queued", last_error=(error or "")[:500], node_id="")

    def stats(self) -> dict[str, int]:
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT status, COUNT(*) FROM tbe_deploy_jobs GROUP BY status")
                rows = cur.fetchall()
        return {r[0]: int(r[1]) for r in rows}

    def count_running_on_node(self, node_id: str) -> int:
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT COUNT(*) FROM tbe_deploy_jobs WHERE status='running' AND node_id=%s",
                    (node_id,),
                )
                return int(cur.fetchone()[0])

    def count_running_for_user(self, user_id: int) -> int:
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT COUNT(*) FROM tbe_deploy_jobs WHERE status='running' AND user_id=%s",
                    (int(user_id),),
                )
                return int(cur.fetchone()[0])
