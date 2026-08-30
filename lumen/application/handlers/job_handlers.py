"""Job use-case handlers — depend only on domain ports."""
from __future__ import annotations

import time
import uuid

from lumen.application.commands.create_job import CreateJobCommand
from lumen.application.queries.get_job import GetJobQuery
from lumen.domain.entities.job import Job
from lumen.domain.repositories.job_repository import JobRepository
from lumen.domain.value_objects.job_status import JobStatus


def handle_create_job(
    cmd: CreateJobCommand,
    *,
    jobs: JobRepository,
) -> Job:
    tid = (cmd.tenant_id or "").strip()
    kind = (cmd.kind or "").strip()
    if not tid:
        raise ValueError("tenant_id_required")
    if not kind:
        raise ValueError("kind_required")
    job = Job(
        job_id=uuid.uuid4().hex,
        tenant_id=tid,
        kind=kind,
        status=JobStatus.QUEUED,
        created_at=time.time(),
        input=dict(cmd.input or {}),
    )
    return jobs.create(job)


def handle_get_job(
    query: GetJobQuery,
    *,
    jobs: JobRepository,
) -> Job:
    jid = (query.job_id or "").strip()
    tid = (query.tenant_id or "").strip()
    if not jid:
        raise ValueError("job_id_required")
    job = jobs.get(jid)
    if job is None:
        raise LookupError("job_not_found")
    if job.tenant_id != tid:
        raise PermissionError("job_not_owned")
    return job
