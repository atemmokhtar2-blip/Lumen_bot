"""Domain State — lives across time. NEVER stored in ArtifactStore."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class RunStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"


class DeploymentStatus(str, Enum):
    STOPPED = "stopped"
    STARTING = "starting"
    RUNNING = "running"
    FAILED = "failed"
    STOPPING = "stopping"


class JobStatus(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class ProjectState:
    project_id: str
    name: str
    owner_id: Optional[str] = None
    tenant_id: Optional[str] = None
    root_path: Optional[str] = None
    created_at: datetime = field(default_factory=_utcnow)
    updated_at: datetime = field(default_factory=_utcnow)
    tags: List[str] = field(default_factory=list)
    extra: Dict[str, Any] = field(default_factory=dict)


@dataclass
class RunState:
    run_id: str
    project_id: Optional[str] = None
    status: RunStatus = RunStatus.PENDING
    request_summary: str = ""
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None
    error: Optional[str] = None
    extra: Dict[str, Any] = field(default_factory=dict)

    def mark_running(self) -> None:
        self.status = RunStatus.RUNNING
        self.started_at = _utcnow()

    def mark_succeeded(self) -> None:
        self.status = RunStatus.SUCCEEDED
        self.finished_at = _utcnow()

    def mark_failed(self, error: str) -> None:
        self.status = RunStatus.FAILED
        self.error = error
        self.finished_at = _utcnow()


@dataclass
class DeploymentState:
    deployment_id: str
    project_id: str
    status: DeploymentStatus = DeploymentStatus.STOPPED
    host: Optional[str] = None
    process_ref: Optional[str] = None
    started_at: Optional[datetime] = None
    stopped_at: Optional[datetime] = None
    last_error: Optional[str] = None
    extra: Dict[str, Any] = field(default_factory=dict)


@dataclass
class JobState:
    job_id: str
    kind: str
    status: JobStatus = JobStatus.QUEUED
    project_id: Optional[str] = None
    run_id: Optional[str] = None
    created_at: datetime = field(default_factory=_utcnow)
    updated_at: datetime = field(default_factory=_utcnow)
    result_ref: Optional[str] = None
    error: Optional[str] = None
    extra: Dict[str, Any] = field(default_factory=dict)


__all__ = [
    "RunStatus", "DeploymentStatus", "JobStatus",
    "ProjectState", "RunState", "DeploymentState", "JobState",
]
