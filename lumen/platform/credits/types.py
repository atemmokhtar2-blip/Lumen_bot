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
    account_id: str = ""
    # Promotional / trial credits (subset of current_balance)
    promotional_balance: int = 0
    promo_expires_at: float = 0.0  # unix ts; 0 = no expiry

    @property
    def available(self) -> int:
        return max(0, int(self.current_balance) - int(self.reserved_balance))

    @property
    def paid_balance(self) -> int:
        """Non-promotional portion of current_balance."""
        return max(0, int(self.current_balance) - int(self.promotional_balance))


@dataclass
class LedgerLeg:
    account_id: str
    side: str  # debit | credit
    amount: int


@dataclass
class LedgerEntry:
    """Transaction header + legs (double-entry)."""
    transaction_id: str
    tenant_id: str
    type: str
    legs: list[LedgerLeg]
    balance_after: int  # user wallet current after tx
    reserved_after: int = 0
    reference_id: str = ""
    idempotency_key: str = ""
    prev_hash: str = ""
    entry_hash: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: float = 0.0

    @property
    def amount(self) -> int:
        """Net effect on user wallet (credit positive / debit negative) for compatibility."""
        for leg in self.legs:
            if leg.account_id.startswith("wallet:"):
                return leg.amount if leg.side == "credit" else -leg.amount
        return 0


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
    ledger_wallet_net: int
    wallet_reserved: int
    unbalanced_transactions: int = 0
    drift_balance: int = 0
    notes: str = ""
