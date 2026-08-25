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
        return int(self.current_balance) - int(self.reserved_balance)


@dataclass
class LedgerEntry:
    transaction_id: str
    tenant_id: str
    amount: int  # +credit / -debit
    balance_after: int
    type: str
    reference_id: str = ""
    idempotency_key: str = ""
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
