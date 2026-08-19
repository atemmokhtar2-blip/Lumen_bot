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
import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Callable

from .sanitize import sanitize_for_storage

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

    def cleanup_old_jobs(self, days: int = 7) -> int:
        """Delete terminal jobs older than `days`. Returns rows deleted."""
        cutoff = time.time() - (max(1, int(days)) * 86400)
        with self._conn() as conn:
            cur = conn.execute(
                "DELETE FROM jobs WHERE created_at < ? AND status IN (?,?,?)",
                (cutoff, STATUS_SUCCEEDED, STATUS_FAILED, STATUS_CANCELLED),
            )
            conn.commit()
            return int(cur.rowcount or 0)

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



    def count_active(self, tenant_id: str | None = None) -> int:
        """Number of jobs in queued or running state."""
        conn = self._conn()
        if tenant_id:
            row = conn.execute(
                "SELECT COUNT(*) FROM jobs WHERE status IN ('queued','running') AND tenant_id=?",
                (str(tenant_id),),
            ).fetchone()
        else:
            row = conn.execute(
                "SELECT COUNT(*) FROM jobs WHERE status IN ('queued','running')",
            ).fetchone()
        return int(row[0]) if row else 0


class RedisJobStore:
    """Durable multi-worker job store on Redis (production backend).

    Keys:
      job:{id}   → JSON hash fields
      jobs:active → set of non-terminal job ids
      jobs:tenant:{tid} → list of recent job ids
    """

    def __init__(self, redis_url: str | None = None) -> None:
        import redis
        url = (redis_url or os.getenv("REDIS_URL") or os.getenv("JOB_REDIS_URL") or "").strip()
        if not url:
            raise ValueError("REDIS_URL required for RedisJobStore")
        self._r = redis.Redis.from_url(url, decode_responses=True)
        self._r.ping()
        self._prefix = (os.getenv("JOB_REDIS_PREFIX") or "tbe:job:").strip() or "tbe:job:"

    def _k(self, job_id: str) -> str:
        return f"{self._prefix}{job_id}"

    def create(self, job: Job) -> Job:
        import json
        key = self._k(job.job_id)
        pipe = self._r.pipeline()
        pipe.hset(
            key,
            mapping={
                "job_id": job.job_id,
                "tenant_id": job.tenant_id,
                "kind": job.kind,
                "status": job.status,
                "created_at": str(job.created_at),
                "started_at": str(job.started_at or 0),
                "finished_at": str(job.finished_at or 0),
                "progress": str(job.progress or 0),
                "message": job.message or "",
                "input_json": json.dumps(job.input or {}, ensure_ascii=False, default=str),
                "result_json": json.dumps(job.result or {}, ensure_ascii=False, default=str),
                "error": job.error or "",
            },
        )
        pipe.sadd(f"{self._prefix}active", job.job_id)
        pipe.lpush(f"{self._prefix}tenant:{job.tenant_id}", job.job_id)
        pipe.ltrim(f"{self._prefix}tenant:{job.tenant_id}", 0, 99)
        pipe.expire(key, int(os.getenv("JOB_REDIS_TTL_SEC") or str(7 * 86400)))
        pipe.execute()
        return job

    def update(self, job_id: str, **fields: Any) -> None:
        import json
        key = self._k(job_id)
        if not self._r.exists(key):
            return
        mapping: dict[str, str] = {}
        for k, v in fields.items():
            if k in {"input", "result"}:
                mapping[f"{k}_json"] = json.dumps(v or {}, ensure_ascii=False, default=str)
            elif k.endswith("_json"):
                mapping[k] = json.dumps(v) if not isinstance(v, str) else v
            else:
                mapping[k] = str(v) if v is not None else ""
        if mapping:
            self._r.hset(key, mapping=mapping)
        status = fields.get("status")
        if status in TERMINAL:
            self._r.srem(f"{self._prefix}active", job_id)
        elif status in {STATUS_QUEUED, STATUS_RUNNING}:
            self._r.sadd(f"{self._prefix}active", job_id)

    def get(self, job_id: str) -> Job | None:
        import json
        data = self._r.hgetall(self._k(job_id))
        if not data:
            return None
        try:
            return Job(
                job_id=data.get("job_id") or job_id,
                tenant_id=data.get("tenant_id") or "",
                kind=data.get("kind") or "",
                status=data.get("status") or STATUS_QUEUED,
                created_at=float(data.get("created_at") or 0),
                started_at=float(data.get("started_at") or 0),
                finished_at=float(data.get("finished_at") or 0),
                progress=float(data.get("progress") or 0),
                message=data.get("message") or "",
                input=json.loads(data.get("input_json") or "{}"),
                result=json.loads(data.get("result_json") or "{}"),
                error=data.get("error") or "",
            )
        except Exception:
            return None

    def cleanup_old_jobs(self, days: int = 7) -> int:
        # TTL on keys handles expiry; active set is pruned opportunistically
        return 0

    def list_for_tenant(self, tenant_id: str, *, limit: int = 20) -> list[Job]:
        ids = self._r.lrange(f"{self._prefix}tenant:{tenant_id}", 0, max(0, limit - 1)) or []
        out: list[Job] = []
        for jid in ids:
            job = self.get(jid)
            if job:
                out.append(job)
        return out

    def count_active(self, tenant_id: str | None = None) -> int:
        if not tenant_id:
            return int(self._r.scard(f"{self._prefix}active") or 0)
        # approximate: scan tenant list for non-terminal
        ids = self._r.lrange(f"{self._prefix}tenant:{tenant_id}", 0, 99) or []
        n = 0
        for jid in ids:
            st = self._r.hget(self._k(jid), "status")
            if st in {STATUS_QUEUED, STATUS_RUNNING}:
                n += 1
        return n


def _is_dev_env() -> bool:
    env = (os.getenv("ENVIRONMENT") or os.getenv("TBE_ENV") or "").strip().lower()
    return env in {"dev", "development", "local", "test"}


def get_job_store(db_path: str | Path | None = None):
    """Select durable job backend.

    Production (ENVIRONMENT not dev/local/test): Redis is **mandatory**.
    SQLite JobStore is refused outside explicit dev environments.
    """
    backend = (os.getenv("JOB_BACKEND") or "").strip().lower()
    redis_url = (os.getenv("JOB_REDIS_URL") or os.getenv("REDIS_URL") or "").strip()

    if _is_dev_env():
        if backend == "redis" or (redis_url and backend != "sqlite"):
            return RedisJobStore(redis_url)
        return JobStore(db_path)

    # Production path — no SQLite
    if not redis_url:
        raise RuntimeError(
            "Production job queue requires Redis. Set REDIS_URL or JOB_REDIS_URL. "
            "SQLite is not allowed outside ENVIRONMENT=dev|local|test."
        )
    if backend == "sqlite":
        raise RuntimeError(
            "JOB_BACKEND=sqlite is refused outside dev. Unset JOB_BACKEND and set REDIS_URL."
        )
    return RedisJobStore(redis_url)


class JobRunner:
    """Dedicated pool — never uses asyncio's default executor for heavy work.

    Foundation limits (env-overridable):
      JOB_MAX_WORKERS          global thread pool size (default 2)
      JOB_MAX_QUEUED_GLOBAL    max non-terminal jobs system-wide (default 100)
      JOB_MAX_QUEUED_PER_TENANT max non-terminal jobs per tenant (default 5)
      JOB_MAX_INPUT_BYTES      max serialized input_json size (default 65536)
    """

    def __init__(self, store=None) -> None:
        self.store = store if store is not None else get_job_store()
        max_workers = int(os.getenv("JOB_MAX_WORKERS") or "2")
        self._pool = ThreadPoolExecutor(
            max_workers=max(1, max_workers),
            thread_name_prefix="job-worker",
        )
        self._handlers: dict[str, Callable[[Job], dict[str, Any]]] = {}
        self._lock = threading.Lock()
        self._max_queued_global = int(os.getenv("JOB_MAX_QUEUED_GLOBAL") or "100")
        self._max_queued_tenant = int(os.getenv("JOB_MAX_QUEUED_PER_TENANT") or "5")
        self._max_input_bytes = int(os.getenv("JOB_MAX_INPUT_BYTES") or "65536")

    def register(self, kind: str, handler: Callable[[Job], dict[str, Any]]) -> None:
        self._handlers[kind] = handler

    def _count_active(self, tenant_id: str | None = None) -> int:
        """Count non-terminal jobs (queued + running)."""
        try:
            return self.store.count_active(tenant_id=tenant_id)
        except Exception:
            # Fallback: list and count if store helper missing mid-upgrade
            if tenant_id:
                jobs = self.store.list_for_tenant(tenant_id, limit=200)
            else:
                jobs = []
            return sum(1 for j in jobs if j.status not in TERMINAL)

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
        if not tenant_id or not str(tenant_id).strip():
            raise ValueError("tenant_id_required")

        # Bound input size before it hits SQLite / workers
        import json as _json
        raw_in = _json.dumps(input_data or {}, ensure_ascii=False, default=str)
        if len(raw_in.encode("utf-8")) > self._max_input_bytes:
            raise ValueError("job_input_too_large")

        with self._lock:
            if self._max_queued_global > 0 and self._count_active() >= self._max_queued_global:
                raise RuntimeError("job_queue_full")
            if (
                self._max_queued_tenant > 0
                and self._count_active(tenant_id) >= self._max_queued_tenant
            ):
                raise RuntimeError("job_queue_tenant_full")

            job = Job(
                job_id=f"job_{uuid.uuid4().hex[:16]}",
                tenant_id=str(tenant_id).strip(),
                kind=kind,
                status=STATUS_QUEUED,
                message=message,
                input=input_data or {},
            )
            self.store.create(job)

        # opportunistic GC of old terminal jobs (at most ~1/50 enqueues)
        if int(job.created_at * 1000) % 50 == 0:
            try:
                self.store.cleanup_old_jobs(days=int(os.getenv("JOB_RETENTION_DAYS") or 7))
            except Exception:
                pass
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
            result = handler(job) or {}
            # Bound result payload stored in SQLite (prevents disk/memory abuse)
            import json as _json
            _max_res = int(os.getenv("JOB_MAX_RESULT_BYTES") or "262144")
            try:
                _raw = _json.dumps(result, ensure_ascii=False, default=str)
                if len(_raw.encode("utf-8")) > _max_res:
                    result = {
                        "ok": bool(result.get("ok", False)),
                        "errors": ["result_truncated"],
                        "project_path": None,
                    }
            except Exception:
                result = {"ok": False, "errors": ["result_not_serializable"]}
            # Handler-reported failure must not be stored as SUCCEEDED
            ok = result.get("ok", True)
            if ok is False:
                self.store.update(
                    job_id,
                    status=STATUS_FAILED,
                    finished_at=time.time(),
                    progress=1.0,
                    message=str(result.get("message") or "handler_reported_failure")[:200],
                    error=sanitize_for_storage(
                        str((result.get("errors") or ["failed"])[0]), max_len=500
                    ),
                    result=result,
                )
            else:
                self.store.update(
                    job_id,
                    status=STATUS_SUCCEEDED,
                    finished_at=time.time(),
                    progress=1.0,
                    message="done",
                    result=result,
                )
        except Exception as exc:
            safe = sanitize_for_storage(str(exc), max_len=500)
            logger.error("job %s failed: %s", job_id, safe)
            self.store.update(
                job_id,
                status=STATUS_FAILED,
                finished_at=time.time(),
                progress=1.0,
                message="failed",
                error=safe,
                result={"error_code": "job_failed"},
            )


_RUNNER: JobRunner | None = None
_HANDLERS_READY = False


def _register_builtin_handlers(runner: JobRunner) -> None:
    def handle_generate(job: Job) -> dict[str, Any]:
        from telegram_bot_engine import generate_bot
        from telegram_bot_engine.services.user_sandbox import get_user_sandbox
        from telegram_bot_engine.services.capability_detection import (
            feature_keys,
            telegram_preflight,
        )
        from b2b_platform.metering import get_metering

        description = str(job.input.get("description") or "").strip()
        # Phase 2: detection gate (same honesty as Telegram consumer)
        pre = telegram_preflight(description)
        report = pre.get("report")
        if pre.get("should_block"):
            return {
                "ok": False,
                "tenant_id": job.tenant_id,
                "project_path": None,
                "ready_for_token": False,
                "verified_commands": [],
                "anti_hallucination": {},
                "errors": [pre.get("user_message") or "capability_blocked"],
                "metadata": {
                    "engine": "spec_core",
                    "zero_ai": True,
                    "blocked_by": "capability_detection",
                    "capability_detection": {
                        "status": getattr(getattr(report, "status", None), "value", None),
                        "reason_ar": getattr(report, "reason_ar", None) if report else None,
                    },
                },
            }

        preferred = feature_keys(report, include_core=True) if report else None
        # Plan engine tier filter (Explorer=basic only — no payments/db)
        try:
            from b2b_platform.plan_gate import filter_preferred_keys
            preferred = filter_preferred_keys(preferred, tenant_id=job.tenant_id)
        except Exception:
            pass
        base = os.getenv("OUTPUT_DIR", "/tmp/generated")
        from api.security import stable_tenant_uid

        uid = stable_tenant_uid(job.tenant_id)
        sandbox = get_user_sandbox(uid, base)
        work = sandbox.new_project_dir(label="api")
        # Hard guarantee: generation work dir is inside this tenant sandbox
        if not sandbox.is_under_sandbox(work):
            return {
                "ok": False,
                "tenant_id": job.tenant_id,
                "project_path": None,
                "errors": ["sandbox_path_invalid"],
            }
        runner.store.update(job.job_id, progress=0.15, message="generating")
        result = generate_bot(
            description,
            str(work),
            user_id=uid,
            preferred_keys=preferred,
        )
        success = bool(getattr(result, "success", False))
        meta = getattr(result, "metadata", None) or {}
        project_path = getattr(result, "project_path", None)
        if project_path and not sandbox.is_under_sandbox(project_path):
            return {
                "ok": False,
                "tenant_id": job.tenant_id,
                "project_path": None,
                "errors": ["project_path_outside_sandbox"],
            }

        errors = list(getattr(result, "errors", None) or [])
        if success and project_path:
            try:
                from b2b_platform.plan_gate import apply_post_generation
                apply_post_generation(str(project_path), tenant_id=job.tenant_id)
            except Exception:
                logger.exception("post-generation plan hooks failed")
        get_metering().record(job.tenant_id, event="generate_completed")
        runner.store.update(job.job_id, progress=0.9, message="finalizing")
        layers = meta.get("layers") if isinstance(meta.get("layers"), dict) else {}
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
                "capability_detection": layers.get("capability_detection")
                or (meta.get("capability_detection")),
                "soft_note": pre.get("soft_note") or "",
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
