"""Tenant persistence port."""
from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

from lumen.domain.entities.tenant import Tenant


@runtime_checkable
class TenantRepository(Protocol):
    def get(self, tenant_id: str) -> Tenant | None: ...

    def authenticate(self, api_key: str) -> Tenant | None: ...

    def create(
        self,
        name: str,
        *,
        plan_id: str = "free",
        owner_telegram_id: int = 0,
        **fields: object,
    ) -> tuple[Tenant, str]:
        """Return (tenant, raw_api_key). raw key shown once."""
        ...

    def update_white_label(self, tenant_id: str, **fields: Any) -> Tenant | None: ...

    def rotate_key(self, tenant_id: str) -> str | None:
        """Return new raw API key once, or None if tenant missing."""
        ...

    def list_all(self) -> list[Tenant]: ...
