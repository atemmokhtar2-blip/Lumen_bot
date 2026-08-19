"""Real job queue: RQ + Redis (CPU-bound generation off the API process).

Production path:
  - API enqueues via enqueue_job()
  - Separate worker: `rq worker tbe --url $REDIS_URL` or python -m b2b_platform.worker

Dev without Redis may fall back to in-process JobRunner (ENVIRONMENT=dev only).
"""
from __future__ import annotations

import logging
import os
import time
import uuid
from typing import Any, Callable

logger = logging.getLogger("b2b.task_queue")

QUEUE_NAME = (os.getenv("RQ_QUEUE_NAME") or "tbe").strip() or "tbe"


def _redis_url() -> str:
    return (os.getenv("JOB_REDIS_URL") or os.getenv("REDIS_URL") or "").strip()


def _is_dev() -> bool:
    env = (os.getenv("ENVIRONMENT") or os.getenv("TBE_ENV") or "").strip().lower()
    return env in {"dev", "development", "local", "test"}


def get_redis():
    import redis
    url = _redis_url()
    if not url:
        raise RuntimeError("REDIS_URL is required for the RQ task queue")
    return redis.Redis.from_url(url)


def get_queue():
    from rq import Queue
    return Queue(QUEUE_NAME, connection=get_redis(), default_timeout=int(os.getenv("RQ_JOB_TIMEOUT") or "600"))


def enqueue_job(
    *,
    tenant_id: str,
    kind: str,
    input_data: dict[str, Any] | None = None,
    message: str = "queued",
) -> dict[str, Any]:
    """Enqueue durable work. Returns public job dict including job_id / rq_id."""
    from .jobs import Job, STATUS_QUEUED, get_job_store

    store = get_job_store()
    job = Job(
        job_id=f"job_{uuid.uuid4().hex[:16]}",
        tenant_id=str(tenant_id).strip(),
        kind=str(kind),
        status=STATUS_QUEUED,
        message=message,
        input=input_data or {},
    )
    store.create(job)

    if not _redis_url():
        if not _is_dev():
            raise RuntimeError("REDIS_URL required to enqueue jobs outside dev")
        # Dev inline
        from .jobs import get_job_runner
        runner = get_job_runner()
        runner._pool.submit(runner._run, job.job_id)
        return job.public_dict()

    q = get_queue()
    rq_job = q.enqueue(
        "b2b_platform.task_queue.execute_stored_job",
        job.job_id,
        job_id=job.job_id,  # RQ job id aligned when possible
        failure_ttl=int(os.getenv("RQ_FAILURE_TTL") or "86400"),
        result_ttl=int(os.getenv("RQ_RESULT_TTL") or "86400"),
    )
    try:
        store.update(job.job_id, message=f"rq:{rq_job.id}")
    except Exception:
        pass
    logger.info("enqueued kind=%s job_id=%s rq_id=%s", kind, job.job_id, rq_job.id)
    return job.public_dict()


def execute_stored_job(job_id: str) -> dict[str, Any]:
    """Worker entry: load job from store and run registered handler."""
    from .jobs import get_job_runner, STATUS_FAILED

    runner = get_job_runner()
    runner._run(job_id)
    job = runner.store.get(job_id)
    if not job:
        return {"ok": False, "error": "missing_job"}
    return {
        "ok": job.status != STATUS_FAILED,
        "job_id": job.job_id,
        "status": job.status,
        "result": job.result,
        "error": job.error,
    }
