"""Durable deploy job queue — API enqueues, workers claim and execute.

Supports tens of thousands of bots by decoupling HTTP/Telegram handlers from
docker build/run (which can take minutes). Backend: SQLite by default, Postgres
when TBE_DATABASE_URL/DATABASE_URL is postgres.

Job lifecycle: queued → claimed → building → running | failed | cancelled
"""
from __future__ import annotations

import json
import logging
import os
import sqlite3
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger("tbe.hosting.deploy_queue")

_SCHEMA = """
CREATE TABLE IF NOT EXISTS deploy_jobs (
  job_id TEXT PRIMARY KEY,
  user_id INTEGER NOT NULL,
  project_path TEXT NOT NULL,
  token_fp TEXT NOT NULL DEFAULT '',
  sealed_token TEXT NOT NULL DEFAULT '',
  status TEXT NOT NULL DEFAULT 'queued',
  node_id TEXT NOT NULL DEFAULT '',
  deployment_id TEXT NOT NULL DEFAULT '',
  image_tag TEXT NOT NULL DEFAULT '',
  attempts INTEGER NOT NULL DEFAULT 0,
  max_attempts INTEGER NOT NULL DEFAULT 3,
  last_error TEXT NOT NULL DEFAULT '',
  created_at REAL NOT NULL,
  updated_at REAL NOT NULL,
  claimed_at REAL NOT NULL DEFAULT 0,
  meta_json TEXT NOT NULL DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS idx_jobs_status ON deploy_jobs(status, created_at);
CREATE INDEX IF NOT EXISTS idx_jobs_user ON deploy_jobs(user_id);
"""


def _db_path() -> Path:
    base = Path(os.environ.get("OUTPUT_DIR") or "/tmp/generated") / "hosting"
    base.mkdir(parents=True, exist_ok=True)
    return base / "deploy_jobs.sqlite3"


@dataclass
class DeployJob:
    job_id: str
    user_id: int
    project_path: str
    token_fp: str
    sealed_token: str
    status: str
    node_id: str = ""
    deployment_id: str = ""
    image_tag: str = ""
    attempts: int = 0
    max_attempts: int = 3
    last_error: str = ""
    created_at: float = 0.0
    updated_at: float = 0.0
    claimed_at: float = 0.0
    meta_json: str = "{}"

    def to_dict(self) -> dict[str, Any]:
        return self.__dict__.copy()


class DeployQueue:
    """SQLite deploy queue — **dev only**. Production must use PgDeployQueue."""

    def __init__(self, path: Path | None = None) -> None:
        env = (os.getenv("ENVIRONMENT") or os.getenv("TBE_ENV") or "").strip().lower()
        if env not in {"dev", "development", "local", "test"}:
            raise RuntimeError(
                "SQLite DeployQueue is forbidden outside ENVIRONMENT=dev. "
                "Set DATABASE_URL (postgresql://...) for PgDeployQueue."
            )
        self.path = Path(path) if path else _db_path()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._init()

    def _conn(self) -> sqlite3.Connection:
        c = sqlite3.connect(str(self.path), timeout=60, check_same_thread=False)
        c.row_factory = sqlite3.Row
        c.execute("PRAGMA journal_mode=WAL")
        c.execute("PRAGMA synchronous=NORMAL")
        return c

    def _init(self) -> None:
        with self._conn() as c:
            c.executescript(_SCHEMA)

    def enqueue(
        self,
        *,
        user_id: int,
        project_path: str,
        bot_token: str,
        meta: dict | None = None,
    ) -> DeployJob:
        import hashlib
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
        with self._conn() as c:
            # Cap queued jobs per user to prevent flood
            max_q = int((os.environ.get("TBE_MAX_QUEUED_PER_USER") or "20").strip() or "20")
            row = c.execute(
                "SELECT COUNT(*) AS n FROM deploy_jobs WHERE user_id=? AND status IN ('queued','claimed','building')",
                (job.user_id,),
            ).fetchone()
            if int(row["n"] if row else 0) >= max_q:
                raise RuntimeError(f"user_queue_full:{max_q}")
            c.execute(
                """
                INSERT INTO deploy_jobs (
                  job_id, user_id, project_path, token_fp, sealed_token, status,
                  node_id, deployment_id, image_tag, attempts, max_attempts,
                  last_error, created_at, updated_at, claimed_at, meta_json
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    job.job_id, job.user_id, job.project_path, job.token_fp, job.sealed_token,
                    job.status, "", "", "", 0, job.max_attempts, "", job.created_at,
                    job.updated_at, 0.0, job.meta_json,
                ),
            )
        return job

    def claim_next(self, node_id: str) -> Optional[DeployJob]:
        """Atomically claim oldest queued job for this worker node."""
        now = time.time()
        with self._conn() as c:
            c.execute("BEGIN IMMEDIATE")
            try:
                row = c.execute(
                    """
                    SELECT * FROM deploy_jobs
                    WHERE status='queued'
                    ORDER BY created_at ASC
                    LIMIT 1
                    """
                ).fetchone()
                if not row:
                    c.execute("COMMIT")
                    return None
                job_id = row["job_id"]
                c.execute(
                    """
                    UPDATE deploy_jobs
                    SET status='claimed', node_id=?, claimed_at=?, updated_at=?, attempts=attempts+1
                    WHERE job_id=? AND status='queued'
                    """,
                    (node_id, now, now, job_id),
                )
                if c.total_changes != 1:
                    c.execute("COMMIT")
                    return None
                c.execute("COMMIT")
            except Exception:
                c.execute("ROLLBACK")
                raise
        return self.get(job_id)

    def get(self, job_id: str) -> Optional[DeployJob]:
        with self._conn() as c:
            row = c.execute("SELECT * FROM deploy_jobs WHERE job_id=?", (job_id,)).fetchone()
        if not row:
            return None
        return DeployJob(**{k: row[k] for k in row.keys()})

    def update(self, job_id: str, **fields: Any) -> None:
        allowed = {
            "status", "node_id", "deployment_id", "image_tag", "last_error",
            "attempts", "updated_at", "claimed_at", "sealed_token",
        }
        fields = {k: v for k, v in fields.items() if k in allowed}
        fields["updated_at"] = time.time()
        if not fields:
            return
        cols = ", ".join(f"{k}=?" for k in fields)
        vals = list(fields.values()) + [job_id]
        with self._conn() as c:
            c.execute(f"UPDATE deploy_jobs SET {cols} WHERE job_id=?", vals)

    def mark_running(self, job_id: str, *, deployment_id: str, image_tag: str) -> None:
        # Drop sealed token once running — reduce secret retention
        self.update(
            job_id,
            status="running",
            deployment_id=deployment_id,
            image_tag=image_tag,
            sealed_token="",
            last_error="",
        )

    def mark_failed(self, job_id: str, error: str) -> None:
        job = self.get(job_id)
        if not job:
            return
        if job.attempts >= job.max_attempts:
            self.update(job_id, status="failed", last_error=(error or "")[:500], sealed_token="")
        else:
            # re-queue for another worker attempt
            self.update(job_id, status="queued", last_error=(error or "")[:500], node_id="")

    def stats(self) -> dict[str, int]:
        with self._conn() as c:
            rows = c.execute(
                "SELECT status, COUNT(*) AS n FROM deploy_jobs GROUP BY status"
            ).fetchall()
        return {r["status"]: int(r["n"]) for r in rows}

    def count_running_on_node(self, node_id: str) -> int:
        with self._conn() as c:
            row = c.execute(
                "SELECT COUNT(*) AS n FROM deploy_jobs WHERE status='running' AND node_id=?",
                (node_id,),
            ).fetchone()
        return int(row["n"] if row else 0)

    def count_running_for_user(self, user_id: int) -> int:
        with self._conn() as c:
            row = c.execute(
                "SELECT COUNT(*) AS n FROM deploy_jobs WHERE status='running' AND user_id=?",
                (int(user_id),),
            ).fetchone()
        return int(row["n"] if row else 0)


_Q: DeployQueue | None = None


def get_deploy_queue():
    """Production: Postgres only (fail-closed). Dev: SQLite allowed without DATABASE_URL."""
    global _Q
    if _Q is not None:
        return _Q
    env = (os.getenv("ENVIRONMENT") or os.getenv("TBE_ENV") or "production").strip().lower()
    is_dev = env in {"dev", "development", "local", "test"}
    try:
        from telegram_bot_engine.services.hosting.pg_deploy_queue import PgDeployQueue, available as pg_available
        if pg_available():
            _Q = PgDeployQueue()
            return _Q
    except Exception as exc:
        if not is_dev:
            raise RuntimeError(
                f"Postgres deploy queue required in production: {type(exc).__name__}: {exc}"
            ) from exc
        logger.warning("postgres deploy queue unavailable in dev: %s", exc)
    if is_dev:
        logger.warning("DEV ONLY: SQLite deploy queue. Set DATABASE_URL for production.")
        _Q = DeployQueue()
        return _Q
    raise RuntimeError(
        "DATABASE_URL (postgresql://...) is required for deploy queue outside ENVIRONMENT=dev. "
        "SQLite deploy_jobs.sqlite3 is not multi-node safe."
    )
