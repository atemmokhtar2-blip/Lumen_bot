from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class GetJobQuery:
    job_id: str
    tenant_id: str  # ownership enforced in handler
