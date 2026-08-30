"""Architecture tests — domain purity + application handlers with in-memory repos."""
from __future__ import annotations

import pytest

from lumen.application.commands.cancel_job import CancelJobCommand
from lumen.application.commands.create_job import CreateJobCommand
from lumen.application.commands.create_tenant import CreateTenantCommand
from lumen.application.commands.pause_job import PauseJobCommand
from lumen.application.commands.resume_job import ResumeJobCommand
from lumen.application.commands.rotate_api_key import RotateApiKeyCommand
from lumen.application.commands.update_white_label import UpdateWhiteLabelCommand
from lumen.application.handlers.job_handlers import (
    handle_cancel_job,
    handle_create_job,
    handle_get_job,
    handle_pause_job,
    handle_resume_job,
)
from lumen.application.handlers.tenant_handlers import (
    handle_authenticate_tenant,
    handle_create_tenant,
    handle_get_tenant,
    handle_rotate_api_key,
    handle_update_white_label,
)
from lumen.application.queries.authenticate_tenant import AuthenticateTenantQuery
from lumen.application.queries.get_job import GetJobQuery
from lumen.application.queries.get_tenant import GetTenantQuery
from lumen.domain.entities.tenant import Tenant
from lumen.domain.value_objects.job_status import JobStatus
from lumen.domain.value_objects.money import Money
from lumen.infrastructure.persistence.memory import (
    InMemoryJobRepository,
    InMemoryTenantRepository,
)


def test_money_value_object():
    m = Money(10.0, "USD")
    assert m.currency == "usd"
    assert m.add(Money(2.5, "usd")).amount == 12.5
    with pytest.raises(ValueError):
        Money(-1.0)


def test_tenant_ensure_active():
    t = Tenant(tenant_id="t1", name="A", active=False)
    with pytest.raises(PermissionError):
        t.ensure_active()


def test_create_and_authenticate_tenant():
    repo = InMemoryTenantRepository()
    tenant, key = handle_create_tenant(
        CreateTenantCommand(name="Acme", plan_id="starter"),
        tenants=repo,
    )
    assert tenant.tenant_id
    assert key.startswith("sk_test_")
    got = handle_authenticate_tenant(
        AuthenticateTenantQuery(api_key=key),
        tenants=repo,
    )
    assert got.tenant_id == tenant.tenant_id
    loaded = handle_get_tenant(GetTenantQuery(tenant_id=tenant.tenant_id), tenants=repo)
    assert loaded.name == "Acme"


def test_update_white_label_and_rotate_key():
    repo = InMemoryTenantRepository()
    tenant, key = handle_create_tenant(CreateTenantCommand(name="BrandCo"), tenants=repo)
    updated = handle_update_white_label(
        UpdateWhiteLabelCommand(tenant_id=tenant.tenant_id, brand_name="NewBrand"),
        tenants=repo,
    )
    assert updated.brand_name == "NewBrand"
    new_key = handle_rotate_api_key(
        RotateApiKeyCommand(tenant_id=tenant.tenant_id),
        tenants=repo,
    )
    assert new_key != key
    with pytest.raises(PermissionError):
        handle_authenticate_tenant(AuthenticateTenantQuery(api_key=key), tenants=repo)
    assert handle_authenticate_tenant(
        AuthenticateTenantQuery(api_key=new_key), tenants=repo
    ).tenant_id == tenant.tenant_id


def test_authenticate_rejects_bad_key():
    repo = InMemoryTenantRepository()
    with pytest.raises(PermissionError):
        handle_authenticate_tenant(
            AuthenticateTenantQuery(api_key="nope"),
            tenants=repo,
        )


def test_job_create_ownership_and_controls():
    tenants = InMemoryTenantRepository()
    jobs = InMemoryJobRepository()
    t, _ = handle_create_tenant(CreateTenantCommand(name="J"), tenants=tenants)
    job = handle_create_job(
        CreateJobCommand(tenant_id=t.tenant_id, kind="generate", input={"q": "bot"}),
        jobs=jobs,
    )
    assert job.status == JobStatus.QUEUED
    loaded = handle_get_job(
        GetJobQuery(job_id=job.job_id, tenant_id=t.tenant_id),
        jobs=jobs,
    )
    assert loaded.job_id == job.job_id
    with pytest.raises(PermissionError):
        handle_get_job(
            GetJobQuery(job_id=job.job_id, tenant_id="other"),
            jobs=jobs,
        )
    paused = handle_pause_job(
        PauseJobCommand(job_id=job.job_id, tenant_id=t.tenant_id), jobs=jobs
    )
    assert paused.status == JobStatus.PAUSED
    resumed = handle_resume_job(
        ResumeJobCommand(job_id=job.job_id, tenant_id=t.tenant_id), jobs=jobs
    )
    assert resumed.status == JobStatus.RUNNING
    cancelled = handle_cancel_job(
        CancelJobCommand(job_id=job.job_id, tenant_id=t.tenant_id), jobs=jobs
    )
    assert cancelled.status == JobStatus.CANCELLED
    with pytest.raises(PermissionError):
        handle_cancel_job(
            CancelJobCommand(job_id=job.job_id, tenant_id="other"), jobs=jobs
        )


def test_domain_has_no_framework_imports():
    """Domain package must stay free of infra/framework imports."""
    import pathlib
    import re
    root = pathlib.Path(__file__).resolve().parents[2] / "lumen" / "domain"
    banned = re.compile(
        r"^\s*(?:from|import)\s+("
        r"aiohttp|telegram|redis|sqlalchemy|pymongo|motor|fastapi|flask|django|"
        r"lumen\.(platform|engine|api|bot|infrastructure)"
        r")\b",
        re.M,
    )
    for path in root.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        m = banned.search(text)
        assert not m, f"{path} has banned import: {m.group(0)}"
