"""Composition root — wire adapters for application handlers.

Presentation layers (Telegram / API) should obtain repositories from here
instead of importing infrastructure details directly.
"""
from __future__ import annotations

from functools import lru_cache

from lumen.domain.repositories.billing_gateway import BillingGateway
from lumen.domain.repositories.job_repository import JobRepository
from lumen.domain.repositories.tenant_repository import TenantRepository


@lru_cache(maxsize=1)
def get_tenant_repository() -> TenantRepository:
    from lumen.infrastructure.persistence.tenant_repo import PlatformTenantRepository
    return PlatformTenantRepository()


@lru_cache(maxsize=1)
def get_job_repository() -> JobRepository:
    from lumen.infrastructure.persistence.job_repo import PlatformJobRepository
    return PlatformJobRepository()


@lru_cache(maxsize=1)
def get_billing_gateway() -> BillingGateway:
    from lumen.infrastructure.persistence.billing_gateway import PlatformBillingGateway
    return PlatformBillingGateway()


def reset_repositories() -> None:
    """Test helper — clear cached wiring."""
    get_tenant_repository.cache_clear()
    get_job_repository.cache_clear()
    get_billing_gateway.cache_clear()
