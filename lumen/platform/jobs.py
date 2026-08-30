"""Async job queue for heavy work (generate / host) — non-blocking API.

Architecture:
  - SQLite job store (survives process restart; multi-worker safe with locks)
  - Dedicated ThreadPoolExecutor with a small max_workers so asyncio's
    default executor is never starved by long generate_bot calls
  - Client gets task_id immediately → polls GET /v1/jobs/{id}

Optional: set JOB_BACKEND=redis later; this module stays the interface.
"""
from __future__ import annotations

import logging

def _cm_default_output_dir() -> str:
    try:
        from lumen.platform.paths import default_output_dir
        return default_output_dir()
    except Exception:
        from pathlib import Path as _P
        p = _P.home() / '.lumen'
        p.mkdir(parents=True, exist_ok=True)
        return str(p)


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

logger = logging.getLogger("lumen.platform.jobs")

STATUS_QUEUED = "queued"
STATUS_RUNNING = "running"
STATUS_PAUSED = "paused"
STATUS_SUCCEEDED = "succeeded"
STATUS_FAILED = "failed"
STATUS_CANCELLED = "cancelled"

TERMINAL = {STATUS_SUCCEEDED, STATUS_FAILED, STATUS_CANCELLED}
ACTIVE = {STATUS_QUEUED, STATUS_RUNNING, STATUS_PAUSED}


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
        # Steer notes belong to the live control plane (Phase E) — visible mid-run.
        raw = []
        try:
            raw = list((self.result or {}).get("steer_notes") or [])
        except Exception:
            raw = []
        notes = [n for n in raw if isinstance(n, dict)][-20:]
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
            "steer_notes": notes,
            "last_steer": notes[-1] if notes else None,
            "poll_after_ms": 1500 if self.status not in TERMINAL else 0,
        }


class JobStore:
    """SQLite job store — **dev only**. Production must use RedisJobStore."""

    def __init__(self, db_path: str | Path | None = None) -> None:
        """SQLite is opt-in local-dev only.

        Hard rules (defense in depth):
        1) Any deploy-platform marker / FORCE_PRODUCTION → always reject.
        2) runtime_config.is_dev() must be True (ENVIRONMENT=dev alone is not enough
           when markers are present).
        3) Explicit ALLOW_SQLITE_JOBSTORE=1 required even in verified dev.
        """
        import os as _os
        try:
            from lumen.platform.tenants import _production_signals_present
            if _production_signals_present():
                raise RuntimeError(
                    "SQLite JobStore forbidden: deploy platform signals present. "
                    "Set REDIS_URL (RedisJobStore is mandatory on this host)."
                )
        except RuntimeError:
            raise
        except Exception:
            pass
        from lumen.platform.runtime_config import is_dev
        if not is_dev():
            raise RuntimeError(
                "SQLite JobStore is forbidden outside verified local dev. "
                "Set REDIS_URL and use RedisJobStore."
            )
        allow = (_os.getenv("ALLOW_SQLITE_JOBSTORE") or "").strip().lower() in {
            "1", "true", "yes", "on",
        }
        if not allow:
            raise RuntimeError(
                "SQLite JobStore requires ALLOW_SQLITE_JOBSTORE=1 even in local dev. "
                "Prefer REDIS_URL / RedisJobStore."
            )
        base = Path(os.getenv("OUTPUT_DIR") or _cm_default_output_dir())
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


    def enqueue_work(self, job_id: str) -> None:
        """Push job id onto the durable work queue (multi-worker safe)."""
        self._r.lpush(f"{self._prefix}queue", job_id)

    def claim_work(self, *, timeout_sec: int = 5) -> str | None:
        """Blocking claim of next job id (BRPOP). Returns job_id or None on timeout."""
        item = self._r.brpop(f"{self._prefix}queue", timeout=max(1, int(timeout_sec)))
        if not item:
            return None
        # brpop returns (key, value)
        return item[1] if isinstance(item, (list, tuple)) else None

    def queue_depth(self) -> int:
        return int(self._r.llen(f"{self._prefix}queue") or 0)

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
    """Delegate to runtime_config.is_dev — deploy markers override ENVIRONMENT=dev."""
    from lumen.platform.runtime_config import is_dev
    return is_dev()


def get_job_store(db_path: str | Path | None = None):
    """Redis is the only job store on deploy hosts; SQLite only with explicit local opt-in.

    Order:
      1) If REDIS_URL → RedisJobStore (always preferred)
      2) Else if verified local dev AND ALLOW_SQLITE_JOBSTORE=1 → JobStore
      3) Else → hard failure (no silent SQLite in production)
    """
    from .runtime_config import redis_url, is_dev, require_production_data_plane
    import os as _os

    require_production_data_plane()

    url = redis_url()
    if url:
        return RedisJobStore(url)

    try:
        from lumen.platform.tenants import _production_signals_present
        if _production_signals_present():
            raise RuntimeError(
                "REDIS_URL is mandatory on deploy platforms "
                "(SQLite JobStore cannot run here)."
            )
    except RuntimeError:
        raise
    except Exception:
        pass

    if is_dev() and (_os.getenv("ALLOW_SQLITE_JOBSTORE") or "").strip().lower() in {
        "1", "true", "yes", "on",
    }:
        return JobStore(db_path)

    raise RuntimeError(
        "REDIS_URL is required for the job store. "
        "SQLite is only available in verified local dev with ALLOW_SQLITE_JOBSTORE=1."
    )



def _register_builtin_handlers(runner: JobRunner) -> None:
    def handle_generate(job: Job) -> dict[str, Any]:
        from lumen.engine import generate_bot
        from lumen.engine.services.user_sandbox import get_user_sandbox
        from lumen.engine.services.capability_detection import (
            feature_keys,
            telegram_preflight,
        )
        from lumen.platform.metering import get_metering

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
                    "engine": "cline",
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
            from lumen.platform.plan_gate import filter_preferred_keys
            preferred = filter_preferred_keys(preferred, tenant_id=job.tenant_id)
        except Exception:
            pass
        base = os.getenv("OUTPUT_DIR") or _cm_default_output_dir()
        from lumen.api.security import stable_tenant_uid

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
        from lumen.engine.services.multi_agent.orchestrator import orchestrate_generate
        result = orchestrate_generate(
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
                from lumen.platform.plan_gate import apply_post_generation
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

    def handle_multi_agent_resume(job: Job) -> dict[str, Any]:
        # redis_board removed — resume via LangGraph SqliteSaver HITL path
        sid = str((job.input or {}).get("state_id") or "").strip()
        if not sid:
            raise ValueError("state_id_required")
        return {
            "ok": False,
            "state_id": sid,
            "status": "use_langgraph_hitl_resume",
            "generated_path": "",
            "final_message": "redis_board removed; use resume_langgraph_hitl",
        }

    runner.register("multi_agent_resume", handle_multi_agent_resume)

    def handle_github_pr_review(job: Job) -> dict[str, Any]:
        """Durable record of PR analysis triggered by webhook."""
        data = dict(job.input or {})
        return {
            "ok": True,
            "repo": data.get("repo"),
            "number": data.get("number"),
            "files": data.get("files") or [],
            "analysis": data.get("analysis") or {},
            "source": "github_webhook",
        }

    runner.register("github_pr_review", handle_github_pr_review)





def get_job_runner() -> JobRunner:
    global _RUNNER, _HANDLERS_READY
    if _RUNNER is None:
        _RUNNER = JobRunner()
    if not _HANDLERS_READY:
        _register_builtin_handlers(_RUNNER)
        _HANDLERS_READY = True
    return _RUNNER
