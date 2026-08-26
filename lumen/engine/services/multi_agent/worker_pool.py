"""Phase B — local worker pool + backpressure for durable resumes.

Complements Temporal workers: when TBE_WORKFLOW_ENGINE=redis_streams|memory,
a process-local pool drains resumable jobs with concurrency limits.
"""
from __future__ import annotations

import logging
import os
import threading
import time
from concurrent.futures import ThreadPoolExecutor, Future
from pathlib import Path
from typing import Any, Callable, Optional

logger = logging.getLogger(__name__)


def _pool_size() -> int:
    try:
        return max(1, min(16, int(os.environ.get("MULTI_AGENT_WORKER_POOL") or "2")))
    except ValueError:
        return 2


def _queue_limit() -> int:
    try:
        return max(1, min(500, int(os.environ.get("MULTI_AGENT_QUEUE_LIMIT") or "50")))
    except ValueError:
        return 50


class WorkerPool:
    """Bounded thread pool with queue backpressure."""

    def __init__(self, max_workers: int | None = None) -> None:
        self._max = max_workers or _pool_size()
        self._executor = ThreadPoolExecutor(max_workers=self._max, thread_name_prefix="lumen-ma")
        self._lock = threading.Lock()
        self._inflight = 0
        self._queued = 0
        self._done = 0
        self._failed = 0

    def submit(self, fn: Callable[..., Any], *args: Any, **kwargs: Any) -> Optional[Future]:
        with self._lock:
            if self._queued + self._inflight >= _queue_limit():
                logger.warning(
                    "worker pool backpressure queue=%s inflight=%s limit=%s",
                    self._queued,
                    self._inflight,
                    _queue_limit(),
                )
                return None
            self._queued += 1

        def _wrap() -> Any:
            with self._lock:
                self._queued = max(0, self._queued - 1)
                self._inflight += 1
            try:
                return fn(*args, **kwargs)
            except Exception:
                with self._lock:
                    self._failed += 1
                raise
            finally:
                with self._lock:
                    self._inflight = max(0, self._inflight - 1)
                    self._done += 1

        return self._executor.submit(_wrap)

    def stats(self) -> dict[str, Any]:
        with self._lock:
            return {
                "max_workers": self._max,
                "inflight": self._inflight,
                "queued": self._queued,
                "done": self._done,
                "failed": self._failed,
                "queue_limit": _queue_limit(),
            }

    def shutdown(self, wait: bool = False) -> None:
        self._executor.shutdown(wait=wait)


_POOL: WorkerPool | None = None
_POOL_LOCK = threading.Lock()


def get_worker_pool() -> WorkerPool:
    global _POOL
    with _POOL_LOCK:
        if _POOL is None:
            _POOL = WorkerPool()
        return _POOL


def submit_resume_job(state_id: str, work_dir: str | Path | None = None) -> dict[str, Any]:
    """Enqueue durable resume on the worker pool (backpressure-aware)."""
    from .durable_workflow import resume_generate

    pool = get_worker_pool()

    def _job() -> dict[str, Any]:
        t0 = time.time()
        state = resume_generate(state_id)
        if state is None:
            return {"ok": False, "error": "no_checkpoint", "state_id": state_id}
        return {
            "ok": True,
            "state_id": state.state_id,
            "status": state.status,
            "qa_passed": bool(state.qa_passed),
            "elapsed_s": round(time.time() - t0, 3),
        }

    fut = pool.submit(_job)
    if fut is None:
        return {"ok": False, "error": "backpressure", "pool": pool.stats()}
    return {"ok": True, "submitted": True, "pool": pool.stats()}


__all__ = ["WorkerPool", "get_worker_pool", "submit_resume_job"]
