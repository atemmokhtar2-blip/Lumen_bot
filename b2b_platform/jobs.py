"""Async job queue for heavy work (generate / host) — non-blocking API.

Architecture:
  - SQLite job store (survives process restart; multi-worker safe with locks)
  - Dedicated ThreadPoolExecutor with a small max_workers so asyncio's
    default executor is never starved by long generate_bot calls
  - Client gets task_id immediately → polls GET /v1/jobs/{id}

Optional: set JOB_BACKEND=redis later; this module stays the interface.
"""
from __future__ import annotations

import json
import logging
import os
import sqlite3
import threading
import time
import traceback
import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Callable

logger = logging.getLogger("b2b_platform.jobs")

STATUS_QUEUED = "queued"
STATUS_RUNNING = "running"
STATUS_SUCCEEDED = "succeeded"
STATUS_FAILED = "failed"
STATUS_CANCELLED = "cancelled"

TERMINAL = {STATUS_SUCCEEDED, STATUS_FAILED, STATUS_CANCELLED}


@dataclass
class Job:
    job_id: str
    tenant_id: str
    kind: str  # generate | host_start | ...
    status: str = STATUS_QUEUED
    created_at: float = field(default_factory=time.time)
    started_at: float = 0.0
    finished_at: float = 0.0
    progress: float = 0.0
    message: str = ""
    input: dict[str, Any] = field(default_factory=dict)
    result: dict[str, Any] = field(default_factory=dict)
    error: str = ""

    def public_dict(self) -> dict[str, Any]:
        return {
            "job_id": self.job_id,
            "tenant_id": self.tenant_id,
            "kind": self.kind,
            "status": self.status,
            "created_at": self.created_at,
            "started_at": self.started_at or None,
            "finished_at": self.finished_at or None,
            "progress": self.progress,
            "message": self.message,
            "result": self.result if self.status in TERMINAL else {},
            "error": self.error if self.status == STATUS_FAILED else "",
            "poll_after_ms": 1500 if self.status not in TERMINAL else 0,
        }


class JobStore:
    def __init__(self, db_path: str | Path | None = None) -> None:
        base = Path(os.getenv("OUTPUT_DIR", "/tmp/generated"))
        self.path = Path(db_path or (base / "platform" / "jobs.sqlite3"))
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._local = threading.local()
        self._init()

    def _conn(self) -> sqlite3.Connection:
        c = getattr(self._local, "conn", None)
        if c is None:
            c = sqlite3.connect(str(self.path), timeout=60, check_same_thread=False)
            c.row_factory = sqlite3.Row
            c.execute("PRAGMA journal_mode=WAL")
            c.execute("PRAGMA synchronous=NORMAL")
            self._local.conn = c
        return c

    def _init(self) -> None:
        with self._conn() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS jobs (
                    job_id TEXT PRIMARY KEY,
                    tenant_id TEXT NOT NULL,
                    kind TEXT NOT NULL,
                    status TEXT NOT NULL,
                    created_at REAL NOT NULL,
                    started_at REAL DEFAULT 0,
                    finished_at REAL DEFAULT 0,
                    progress REAL DEFAULT 0,
                    message TEXT DEFAULT '',
                    input_json TEXT DEFAULT '{}',
                    result_json TEXT DEFAULT '{}',
                    error TEXT DEFAULT ''
                )
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_jobs_tenant ON jobs(tenant_id, created_at)"
            )
            conn.commit()

    def create(self, job: Job) -> Job:
        with self._conn() as conn:
            conn.execute(
                """
                INSERT INTO jobs(
                    job_id, tenant_id, kind, status, created_at, started_at,
                    finished_at, progress, message, input_json, result_json, error
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    job.job_id,
                    job.tenant_id,
                    job.kind,
                    job.status,
                    job.created_at,
                    job.started_at,
                    job.finished_at,
                    job.progress,
                    job.message,
                    json.dumps(job.input, ensure_ascii=False),
                    json.dumps(job.result, ensure_ascii=False),
                    job.error,
                ),
            )
            conn.commit()
        return job

    def update(self, job_id: str, **fields: Any) -> None:
        allowed = {
            "status",
            "started_at",
            "finished_at",
            "progress",
            "message",
            "error",
        }
        sets = []
        vals: list[Any] = []
        for k, v in fields.items():
            if k == "result":
                sets.append("result_json=?")
                vals.append(json.dumps(v, ensure_ascii=False))
            elif k == "input":
                sets.append("input_json=?")
                vals.append(json.dumps(v, ensure_ascii=False))
            elif k in allowed:
                sets.append(f"{k}=?")
                vals.append(v)
        if not sets:
            return
        vals.append(job_id)
        with self._conn() as conn:
            conn.execute(f"UPDATE jobs SET {', '.join(sets)} WHERE job_id=?", vals)
            conn.commit()

    def get(self, job_id: str) -> Job | None:
        with self._conn() as conn:
            row = conn.execute("SELECT * FROM jobs WHERE job_id=?", (job_id,)).fetchone()
        if not row:
            return None
        return Job(
            job_id=row["job_id"],
            tenant_id=row["tenant_id"],
            kind=row["kind"],
            status=row["status"],
            created_at=row["created_at"],
            started_at=row["started_at"] or 0.0,
            finished_at=row["finished_at"] or 0.0,
            progress=row["progress"] or 0.0,
            message=row["message"] or "",
            input=json.loads(row["input_json"] or "{}"),
            result=json.loads(row["result_json"] or "{}"),
            error=row["error"] or "",
        )

    def list_for_tenant(self, tenant_id: str, *, limit: int = 20) -> list[Job]:
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT * FROM jobs WHERE tenant_id=? ORDER BY created_at DESC LIMIT ?",
                (tenant_id, int(limit)),
            ).fetchall()
        out = []
        for row in rows:
            out.append(
                Job(
                    job_id=row["job_id"],
                    tenant_id=row["tenant_id"],
                    kind=row["kind"],
                    status=row["status"],
                    created_at=row["created_at"],
                    started_at=row["started_at"] or 0.0,
                    finished_at=row["finished_at"] or 0.0,
                    progress=row["progress"] or 0.0,
                    message=row["message"] or "",
                    input=json.loads(row["input_json"] or "{}"),
                    result=json.loads(row["result_json"] or "{}"),
                    error=row["error"] or "",
                )
            )
        return out


class JobRunner:
    """Dedicated pool — never uses asyncio's default executor for heavy work."""

    def __init__(self, store: JobStore | None = None) -> None:
        self.store = store or JobStore()
        max_workers = int(os.getenv("JOB_MAX_WORKERS") or "2")
        self._pool = ThreadPoolExecutor(
            max_workers=max(1, max_workers),
            thread_name_prefix="job-worker",
        )
        self._handlers: dict[str, Callable[[Job], dict[str, Any]]] = {}
        self._lock = threading.Lock()

    def register(self, kind: str, handler: Callable[[Job], dict[str, Any]]) -> None:
        self._handlers[kind] = handler

    def enqueue(
        self,
        *,
        tenant_id: str,
        kind: str,
        input_data: dict[str, Any],
        message: str = "queued",
    ) -> Job:
        if kind not in self._handlers:
            raise ValueError(f"unknown_job_kind:{kind}")
        job = Job(
            job_id=f"job_{uuid.uuid4().hex[:16]}",
            tenant_id=tenant_id,
            kind=kind,
            status=STATUS_QUEUED,
            message=message,
            input=input_data,
        )
        self.store.create(job)
        self._pool.submit(self._run, job.job_id)
        return job

    def _run(self, job_id: str) -> None:
        job = self.store.get(job_id)
        if not job:
            return
        handler = self._handlers.get(job.kind)
        if not handler:
            self.store.update(
                job_id,
                status=STATUS_FAILED,
                finished_at=time.time(),
                error="no_handler",
            )
            return
        self.store.update(
            job_id,
            status=STATUS_RUNNING,
            started_at=time.time(),
            progress=0.05,
            message="running",
        )
        try:
            result = handler(job)
            self.store.update(
                job_id,
                status=STATUS_SUCCEEDED,
                finished_at=time.time(),
                progress=1.0,
                message="done",
                result=result or {},
            )
        except Exception as exc:
            logger.exception("job %s failed", job_id)
            self.store.update(
                job_id,
                status=STATUS_FAILED,
                finished_at=time.time(),
                progress=1.0,
                message="failed",
                error=str(exc)[:500],
                result={"traceback": traceback.format_exc()[-1500:]},
            )


_RUNNER: JobRunner | None = None
_HANDLERS_READY = False


def _register_builtin_handlers(runner: JobRunner) -> None:
    def handle_generate(job: Job) -> dict[str, Any]:
        from telegram_bot_engine import generate_bot
        from telegram_bot_engine.services.user_sandbox import get_user_sandbox
        from b2b_platform.metering import get_metering

        description = str(job.input.get("description") or "").strip()
        base = os.getenv("OUTPUT_DIR", "/tmp/generated")
        work = get_user_sandbox(
            abs(hash(job.tenant_id)) % (10**9), base
        ).new_project_dir(label="api")
        runner.store.update(job.job_id, progress=0.15, message="generating")
        result = generate_bot(description, str(work))
        success = bool(getattr(result, "success", False))
        meta = getattr(result, "metadata", None) or {}
        project_path = getattr(result, "project_path", None)
        errors = list(getattr(result, "errors", None) or [])
        get_metering().record(job.tenant_id, event="generate_completed")
        runner.store.update(job.job_id, progress=0.9, message="finalizing")
        return {
            "ok": success,
            "tenant_id": job.tenant_id,
            "project_path": project_path,
            "ready_for_token": bool(meta.get("ready_for_token")),
            "verified_commands": meta.get("verified_commands") or [],
            "anti_hallucination": meta.get("anti_hallucination") or {},
            "errors": errors,
            "metadata": {
                "engine": meta.get("engine"),
                "preset": meta.get("preset"),
                "zero_ai": True,
                "elapsed_ms": meta.get("elapsed_ms"),
            },
        }

    runner.register("generate", handle_generate)


def get_job_runner() -> JobRunner:
    global _RUNNER, _HANDLERS_READY
    if _RUNNER is None:
        _RUNNER = JobRunner()
    if not _HANDLERS_READY:
        _register_builtin_handlers(_RUNNER)
        _HANDLERS_READY = True
    return _RUNNER
