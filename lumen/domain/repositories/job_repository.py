"""Job persistence + control port."""
from __future__ import annotations

from typing import Protocol, runtime_checkable

from lumen.domain.entities.job import Job


@runtime_checkable
class JobRepository(Protocol):
    def get(self, job_id: str) -> Job | None: ...

    def create(self, job: Job) -> Job: ...

    def list_for_tenant(self, tenant_id: str, *, limit: int = 20) -> list[Job]: ...

    def cancel(self, job_id: str, *, tenant_id: str) -> Job | None: ...

    def pause(self, job_id: str, *, tenant_id: str) -> Job | None: ...

    def resume(self, job_id: str, *, tenant_id: str) -> Job | None: ...
