"""TenantRepository — storage-agnostic contract for tenant identity.

Production implementation: PostgresTenantStore (psycopg / PostgreSQL).
Dev implementation: file TenantStore (ENVIRONMENT=dev only).

Business logic (billing, auth, API routes) must depend on this interface
via get_tenant_store(), never on file locks or driver details.
"""
from __future__ import annotations

from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class TenantRepository(Protocol):
    def create(
        self,
        name: str,
        *,
        plan_id: str = "free",
        brand_name: str = "",
        owner_telegram_id: int = 0,
        **wl: Any,
    ) -> tuple[Any, str]:
        """Return (tenant, raw_api_key_once)."""
        ...

    def authenticate(self, api_key: str) -> Any | None:
        ...

    def get(self, tenant_id: str) -> Any | None:
        ...

    def get_by_telegram(self, owner_telegram_id: int) -> Any | None:
        ...

    def list_all(self) -> list[Any]:
        ...

    def set_plan(
        self,
        tenant_id: str,
        plan_id: str,
        *,
        metadata_updates: dict[str, Any] | None = None,
        active: bool = True,
    ) -> bool:
        ...

    def rotate_key(self, tenant_id: str) -> str | None:
        ...

    def update_white_label(self, tenant_id: str, **fields: Any) -> Any | None:
        ...
