"""Repository ports (interfaces only — no implementations here)."""
from lumen.domain.repositories.tenant_repository import TenantRepository
from lumen.domain.repositories.job_repository import JobRepository

__all__ = ["TenantRepository", "JobRepository"]
