"""Architecture tests — domain purity + application handlers with in-memory repos."""
from __future__ import annotations

import pytest

from lumen.application.commands.create_job import CreateJobCommand
from lumen.application.commands.create_tenant import CreateTenantCommand
from lumen.application.handlers.job_handlers import handle_create_job, handle_get_job
from lumen.application.handlers.tenant_handlers import (
    handle_authenticate_tenant,
    handle_create_tenant,
    handle_get_tenant,
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


def test_authenticate_rejects_bad_key():
    repo = InMemoryTenantRepository()
    with pytest.raises(PermissionError):
        handle_authenticate_tenant(
            AuthenticateTenantQuery(api_key="nope"),
            tenants=repo,
        )


def test_job_create_and_ownership():
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
