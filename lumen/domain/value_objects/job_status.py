"""Job lifecycle statuses — pure constants."""
from __future__ import annotations


class JobStatus:
    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"
    PAUSED = "paused"

    TERMINAL = frozenset({SUCCEEDED, FAILED, CANCELLED})
    ACTIVE = frozenset({QUEUED, RUNNING, PAUSED})
