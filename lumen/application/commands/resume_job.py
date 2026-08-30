from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ResumeJobCommand:
    job_id: str
    tenant_id: str
