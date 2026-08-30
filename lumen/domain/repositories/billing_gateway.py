"""Billing / balance port — no infrastructure types."""
from __future__ import annotations

from typing import Protocol, runtime_checkable

from lumen.domain.entities.balance import Balance


@runtime_checkable
class BillingGateway(Protocol):
    """Enforcement gates + balance reads (implemented in infrastructure)."""

    def get_balance(self, tenant_id: str) -> Balance: ...

    def enforce_api(self, tenant_id: str) -> tuple[bool, str]:
        """Return (ok, reason). reason is stable machine code."""
        ...

    def enforce_generation(
        self, tenant_id: str, *, reserve: bool = True
    ) -> tuple[bool, str]: ...

    def enforce_hosting(
        self, tenant_id: str, current_hosted: int
    ) -> tuple[bool, str]: ...

    def enforce_feature(self, tenant_id: str, feature: str) -> tuple[bool, str]: ...
