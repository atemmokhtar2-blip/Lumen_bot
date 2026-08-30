"""JobRepository adapter over existing platform job runner/store."""
from __future__ import annotations

from lumen.domain.entities.job import Job


def _to_domain(raw: object) -> Job | None:
    if raw is None:
        return None
    return Job(
        job_id=str(getattr(raw, "job_id", "") or ""),
        tenant_id=str(getattr(raw, "tenant_id", "") or ""),
        kind=str(getattr(raw, "kind", "") or ""),
        status=str(getattr(raw, "status", "queued") or "queued"),
        created_at=float(getattr(raw, "created_at", 0.0) or 0.0),
        started_at=float(getattr(raw, "started_at", 0.0) or 0.0),
        finished_at=float(getattr(raw, "finished_at", 0.0) or 0.0),
        progress=float(getattr(raw, "progress", 0.0) or 0.0),
        message=str(getattr(raw, "message", "") or ""),
        error=str(getattr(raw, "error", "") or ""),
        input=dict(getattr(raw, "input", None) or {}),
        result=dict(getattr(raw, "result", None) or {}),
    )


class PlatformJobRepository:
    def __init__(self, store: object | None = None) -> None:
        if store is None:
            from lumen.platform.jobs import get_job_runner
            store = get_job_runner().store
        self._store = store

    def get(self, job_id: str) -> Job | None:
        return _to_domain(self._store.get(job_id))

    def create(self, job: Job) -> Job:
        # Build a platform Job if the store expects that type
        try:
            from lumen.platform.jobs import Job as PlatformJob
            pj = PlatformJob(
                job_id=job.job_id,
                tenant_id=job.tenant_id,
                kind=job.kind,
                status=job.status,
                created_at=job.created_at,
                started_at=job.started_at,
                finished_at=job.finished_at,
                progress=job.progress,
                message=job.message,
                error=job.error,
                input=job.input,
                result=job.result,
            )
            saved = self._store.create(pj)
        except Exception:
            saved = self._store.create(job)
        return _to_domain(saved) or job

    def list_for_tenant(self, tenant_id: str, *, limit: int = 20) -> list[Job]:
        rows = self._store.list_for_tenant(tenant_id, limit=limit)
        out: list[Job] = []
        for r in rows or []:
            d = _to_domain(r)
            if d is not None:
                out.append(d)
        return out
