from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass
class Wallet:
    tenant_id: str
    current_balance: int = 0
    reserved_balance: int = 0
    currency: str = "credits"
    updated_at: float = 0.0

    @property
    def available(self) -> int:
        return max(0, int(self.current_balance) - int(self.reserved_balance))


@dataclass
class LedgerEntry:
    transaction_id: str
    tenant_id: str
    amount: int  # effect on current_balance (+ in / - out)
    balance_after: int
    type: str
    reference_id: str = ""
    idempotency_key: str = ""
    reservation_delta: int = 0  # +hold / -release-or-capture
    reserved_after: int = 0
    counterparty: str = "system"
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: float = 0.0


@dataclass
class PricingRule:
    resource_type: str
    cost_per_unit: int
    is_active: bool = True
    version: int = 1
    description: str = ""


@dataclass
class CreditResult:
    ok: bool
    reason: str = "ok"
    wallet: Optional[Wallet] = None
    entry: Optional[LedgerEntry] = None
    transaction_id: str = ""


@dataclass
class ReconcileReport:
    ok: bool
    tenant_id: str
    wallet_balance: int
    ledger_sum: int
    wallet_reserved: int
    ledger_reservation_sum: int
    drift_balance: int = 0
    drift_reserved: int = 0
