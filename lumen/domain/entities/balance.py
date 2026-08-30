"""Tenant credit balance — pure domain (no ledger I/O)."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class Balance:
    """Wallet snapshot for a tenant.

    Units are integer credits (not fiat). available = current - reserved.
    """

    tenant_id: str
    current: int = 0
    reserved: int = 0
    promotional: int = 0
    currency: str = "credits"
    updated_at: float = 0.0
    promo_expires_at: float = 0.0

    @property
    def available(self) -> int:
        return max(0, int(self.current) - int(self.reserved))

    @property
    def paid(self) -> int:
        return max(0, int(self.current) - int(self.promotional))

    def ensure_available(self, amount: int) -> None:
        need = max(0, int(amount))
        if self.available < need:
            raise PermissionError(f"insufficient_credits:{self.available}<{need}")

    def public_dict(self) -> dict:
        return {
            "tenant_id": self.tenant_id,
            "current": int(self.current),
            "reserved": int(self.reserved),
            "available": self.available,
            "promotional": int(self.promotional),
            "paid": self.paid,
            "currency": self.currency,
            "updated_at": self.updated_at,
            "promo_expires_at": self.promo_expires_at or None,
        }
