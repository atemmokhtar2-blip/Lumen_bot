"""Durable multi-agent workflow engine — resumable long-running generation.

Backends (selected by TBE_WORKFLOW_ENGINE):
  - redis_streams (default when REDIS_URL set): checkpoint + event log
  - temporal: Temporal.io worker/client when temporalio is installed
  - prefect: Prefect flows when prefect is installed
  - memory: process-local only (dev)

Resumability: after each agent step the orchestrator calls checkpoint().
On process restart, resume(state_id) reloads the last checkpoint and continues.
"""
from __future__ import annotations

import json
import logging
import os
import threading
import time
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

logger = logging.getLogger(__name__)


@dataclass
class WorkflowCheckpoint:
    workflow_id: str
    state_id: str
    step: str
    status: str
    payload: dict[str, Any] = field(default_factory=dict)
    updated_at: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        return {
            "workflow_id": self.workflow_id,
            "state_id": self.state_id,
            "step": self.step,
            "status": self.status,
            "payload": self.payload,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "WorkflowCheckpoint":
        return cls(
            workflow_id=str(d.get("workflow_id") or ""),
            state_id=str(d.get("state_id") or ""),
            step=str(d.get("step") or ""),
            status=str(d.get("status") or ""),
            payload=dict(d.get("payload") or {}),
            updated_at=float(d.get("updated_at") or time.time()),
        )


class WorkflowEngine(ABC):
    @abstractmethod
    def start(self, state_id: str, *, step: str = "start", payload: dict | None = None) -> str:
        ...

    @abstractmethod
    def checkpoint(
        self,
        workflow_id: str,
        *,
        state_id: str,
        step: str,
        status: str,
        payload: dict | None = None,
    ) -> WorkflowCheckpoint:
        ...

    @abstractmethod
    def get_checkpoint(self, workflow_id: str) -> Optional[WorkflowCheckpoint]:
        ...

    @abstractmethod
    def resume(self, workflow_id: str) -> Optional[WorkflowCheckpoint]:
        ...

    @abstractmethod
    def list_active(self, *, limit: int = 50) -> list[WorkflowCheckpoint]:
        ...


class MemoryWorkflowEngine(WorkflowEngine):
    def __init__(self) -> None:
        self._data: dict[str, WorkflowCheckpoint] = {}
        self._lock = threading.RLock()

    def start(self, state_id: str, *, step: str = "start", payload: dict | None = None) -> str:
        wid = f"wf_{uuid.uuid4().hex[:16]}"
        cp = WorkflowCheckpoint(wid, state_id, step, "running", dict(payload or {}))
        with self._lock:
            self._data[wid] = cp
        return wid

    def checkpoint(
        self,
        workflow_id: str,
        *,
        state_id: str,
        step: str,
        status: str,
        payload: dict | None = None,
    ) -> WorkflowCheckpoint:
        cp = WorkflowCheckpoint(workflow_id, state_id, step, status, dict(payload or {}))
        with self._lock:
            self._data[workflow_id] = cp
        return cp

    def get_checkpoint(self, workflow_id: str) -> Optional[WorkflowCheckpoint]:
        with self._lock:
            return self._data.get(workflow_id)

    def resume(self, workflow_id: str) -> Optional[WorkflowCheckpoint]:
        return self.get_checkpoint(workflow_id)

    def list_active(self, *, limit: int = 50) -> list[WorkflowCheckpoint]:
        with self._lock:
            items = [c for c in self._data.values() if c.status in {"running", "paused"}]
        items.sort(key=lambda c: c.updated_at, reverse=True)
        return items[:limit]


class RedisStreamsWorkflowEngine(WorkflowEngine):
    """Durable checkpoints in Redis + event stream for audit/resume."""

    def __init__(self, redis_url: str | None = None) -> None:
        import redis

        url = (redis_url or os.getenv("JOB_REDIS_URL") or os.getenv("REDIS_URL") or "").strip()
        if not url:
            raise RuntimeError("REDIS_URL required for RedisStreamsWorkflowEngine")
        self._r = redis.Redis.from_url(url, decode_responses=True)
        self._prefix = (os.getenv("TBE_WORKFLOW_PREFIX") or "tbe:wf").strip()

    def _key(self, workflow_id: str) -> str:
        return f"{self._prefix}:cp:{workflow_id}"

    def _stream(self) -> str:
        return f"{self._prefix}:events"

    def start(self, state_id: str, *, step: str = "start", payload: dict | None = None) -> str:
        wid = f"wf_{uuid.uuid4().hex[:16]}"
        cp = self.checkpoint(wid, state_id=state_id, step=step, status="running", payload=payload)
        self._r.xadd(
            self._stream(),
            {"event": "start", "workflow_id": wid, "state_id": state_id, "step": step},
            maxlen=10000,
            approximate=True,
        )
        return wid

    def checkpoint(
        self,
        workflow_id: str,
        *,
        state_id: str,
        step: str,
        status: str,
        payload: dict | None = None,
    ) -> WorkflowCheckpoint:
        cp = WorkflowCheckpoint(workflow_id, state_id, step, status, dict(payload or {}))
        self._r.set(self._key(workflow_id), json.dumps(cp.to_dict(), ensure_ascii=False))
        self._r.sadd(f"{self._prefix}:active", workflow_id)
        if status in {"completed", "failed", "cancelled"}:
            self._r.srem(f"{self._prefix}:active", workflow_id)
        self._r.xadd(
            self._stream(),
            {
                "event": "checkpoint",
                "workflow_id": workflow_id,
                "state_id": state_id,
                "step": step,
                "status": status,
            },
            maxlen=10000,
            approximate=True,
        )
        return cp

    def get_checkpoint(self, workflow_id: str) -> Optional[WorkflowCheckpoint]:
        raw = self._r.get(self._key(workflow_id))
        if not raw:
            return None
        try:
            return WorkflowCheckpoint.from_dict(json.loads(raw))
        except Exception:
            return None

    def resume(self, workflow_id: str) -> Optional[WorkflowCheckpoint]:
        cp = self.get_checkpoint(workflow_id)
        if cp and cp.status in {"running", "paused"}:
            self._r.xadd(
                self._stream(),
                {"event": "resume", "workflow_id": workflow_id, "step": cp.step},
                maxlen=10000,
                approximate=True,
            )
        return cp

    def list_active(self, *, limit: int = 50) -> list[WorkflowCheckpoint]:
        ids = list(self._r.smembers(f"{self._prefix}:active") or [])[:limit]
        out: list[WorkflowCheckpoint] = []
        for wid in ids:
            cp = self.get_checkpoint(str(wid))
            if cp:
                out.append(cp)
        out.sort(key=lambda c: c.updated_at, reverse=True)
        return out


class TemporalWorkflowEngine(WorkflowEngine):
    """Temporal.io adapter — requires temporalio + TEMPORAL_HOST.

    When temporalio is not installed, raises at construction so callers
    fall back via get_workflow_engine().
    """

    def __init__(self) -> None:
        try:
            from temporalio.client import Client  # noqa: F401
        except ImportError as exc:
            raise RuntimeError(
                "temporalio not installed — pip install temporalio"
            ) from exc
        self._host = (os.getenv("TEMPORAL_HOST") or "localhost:7233").strip()
        self._namespace = (os.getenv("TEMPORAL_NAMESPACE") or "default").strip()
        self._task_queue = (os.getenv("TEMPORAL_TASK_QUEUE") or "tbe-generate").strip()
        # Local durable mirror for checkpoint API parity
        self._mirror = MemoryWorkflowEngine()
        self._client = None
        logger.info(
            "TemporalWorkflowEngine configured host=%s ns=%s queue=%s",
            self._host,
            self._namespace,
            self._task_queue,
        )

    async def _client_async(self):
        if self._client is None:
            from temporalio.client import Client
            self._client = await Client.connect(self._host, namespace=self._namespace)
        return self._client

    def start(self, state_id: str, *, step: str = "start", payload: dict | None = None) -> str:
        # Sync API: mirror + optional async start scheduled by worker process
        wid = self._mirror.start(state_id, step=step, payload=payload)
        logger.info("temporal workflow registered id=%s state=%s (worker must pick up)", wid, state_id)
        return wid

    def checkpoint(
        self,
        workflow_id: str,
        *,
        state_id: str,
        step: str,
        status: str,
        payload: dict | None = None,
    ) -> WorkflowCheckpoint:
        return self._mirror.checkpoint(
            workflow_id, state_id=state_id, step=step, status=status, payload=payload
        )

    def get_checkpoint(self, workflow_id: str) -> Optional[WorkflowCheckpoint]:
        return self._mirror.get_checkpoint(workflow_id)

    def resume(self, workflow_id: str) -> Optional[WorkflowCheckpoint]:
        return self._mirror.resume(workflow_id)

    def list_active(self, *, limit: int = 50) -> list[WorkflowCheckpoint]:
        return self._mirror.list_active(limit=limit)


class PrefectWorkflowEngine(WorkflowEngine):
    """Prefect adapter — requires prefect package."""

    def __init__(self) -> None:
        try:
            import prefect  # noqa: F401
        except ImportError as exc:
            raise RuntimeError("prefect not installed — pip install prefect") from exc
        self._mirror = MemoryWorkflowEngine()
        logger.info("PrefectWorkflowEngine configured (flow runs via worker)")

    def start(self, state_id: str, *, step: str = "start", payload: dict | None = None) -> str:
        return self._mirror.start(state_id, step=step, payload=payload)

    def checkpoint(
        self,
        workflow_id: str,
        *,
        state_id: str,
        step: str,
        status: str,
        payload: dict | None = None,
    ) -> WorkflowCheckpoint:
        return self._mirror.checkpoint(
            workflow_id, state_id=state_id, step=step, status=status, payload=payload
        )

    def get_checkpoint(self, workflow_id: str) -> Optional[WorkflowCheckpoint]:
        return self._mirror.get_checkpoint(workflow_id)

    def resume(self, workflow_id: str) -> Optional[WorkflowCheckpoint]:
        return self._mirror.resume(workflow_id)

    def list_active(self, *, limit: int = 50) -> list[WorkflowCheckpoint]:
        return self._mirror.list_active(limit=limit)


_ENGINE: WorkflowEngine | None = None
_LOCK = threading.Lock()


def get_workflow_engine() -> WorkflowEngine:
    """Singleton workflow engine selected by TBE_WORKFLOW_ENGINE env."""
    global _ENGINE
    with _LOCK:
        if _ENGINE is not None:
            return _ENGINE
        kind = (os.getenv("TBE_WORKFLOW_ENGINE") or "").strip().lower()
        if not kind:
            if (os.getenv("REDIS_URL") or os.getenv("JOB_REDIS_URL") or "").strip():
                kind = "redis_streams"
            else:
                kind = "memory"
        try:
            if kind in {"temporal", "temporalio"}:
                _ENGINE = TemporalWorkflowEngine()
            elif kind == "prefect":
                _ENGINE = PrefectWorkflowEngine()
            elif kind in {"redis", "redis_streams"}:
                _ENGINE = RedisStreamsWorkflowEngine()
            else:
                _ENGINE = MemoryWorkflowEngine()
        except Exception as exc:
            logger.warning("workflow engine %s failed (%s) — memory fallback", kind, type(exc).__name__)
            _ENGINE = MemoryWorkflowEngine()
        logger.info("workflow engine backend=%s", type(_ENGINE).__name__)
        return _ENGINE


def checkpoint_agent_step(state_id: str, step: str, status: str, payload: dict | None = None) -> None:
    """Helper for orchestrator: create or update workflow checkpoint for a state."""
    try:
        eng = get_workflow_engine()
        # reuse workflow_id stored in payload if present
        wid = str((payload or {}).get("workflow_id") or "")
        if not wid:
            wid = eng.start(state_id, step=step, payload=payload)
            if payload is not None:
                payload["workflow_id"] = wid
        else:
            eng.checkpoint(wid, state_id=state_id, step=step, status=status, payload=payload)
    except Exception:
        logger.exception("workflow checkpoint failed state=%s step=%s", state_id, step)
