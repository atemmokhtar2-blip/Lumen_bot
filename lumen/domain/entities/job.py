"""Async job aggregate (generate / host / …)."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from lumen.domain.value_objects.job_status import JobStatus


@dataclass
class Job:
    job_id: str
    tenant_id: str
    kind: str
    status: str = JobStatus.QUEUED
    created_at: float = 0.0
    started_at: float = 0.0
    finished_at: float = 0.0
    progress: float = 0.0
    message: str = ""
    error: str = ""
    input: dict[str, Any] = field(default_factory=dict)
    result: dict[str, Any] = field(default_factory=dict)

    def is_terminal(self) -> bool:
        return self.status in JobStatus.TERMINAL

    def public_dict(self) -> dict[str, Any]:
        notes: list = []
        try:
            raw = list((self.result or {}).get("steer_notes") or [])
            notes = [n for n in raw if isinstance(n, dict)][-20:]
        except Exception:
            notes = []
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
            "result": self.result if self.is_terminal() else {},
            "error": self.error if self.status == JobStatus.FAILED else "",
            "steer_notes": notes,
            "last_steer": notes[-1] if notes else None,
            "poll_after_ms": 1500 if not self.is_terminal() else 0,
        }
