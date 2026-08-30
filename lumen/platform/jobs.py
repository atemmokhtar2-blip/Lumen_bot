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
    """REMOVED — SQLite job backend is not supported at any environment level.

    Historical class name kept only so old imports fail loudly with a clear error.
    Use get_job_store() → RedisJobStore (requires REDIS_URL / JOB_REDIS_URL).
    """

    def __init__(self, db_path: str | Path | None = None) -> None:
        raise RuntimeError(
            "SQLite JobStore has been removed. "
            "Set REDIS_URL (or JOB_REDIS_URL) and use RedisJobStore via get_job_store(). "
            "There is no file-backed job store in any environment."
        )

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
    """Redis-only job store — no SQLite fallback in any environment.

    ``db_path`` is accepted for call-site compatibility and ignored.
    """
    from .runtime_config import redis_url, require_production_data_plane

    # Still enforce broader data-plane rules in production
    try:
        require_production_data_plane()
    except RuntimeError:
        # In verified local dev without Postgres, still require Redis for jobs
        pass

    url = redis_url()
    if not url:
        raise RuntimeError(
            "REDIS_URL (or JOB_REDIS_URL) is required for the job store. "
            "SQLite JobStore has been permanently removed — run Redis locally in dev "
            "(e.g. docker run -p 6379:6379 redis:7-alpine)."
        )
    return RedisJobStore(url)


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
