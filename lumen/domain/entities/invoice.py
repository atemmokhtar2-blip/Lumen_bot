"""Billing invoice entity."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class Invoice:
    invoice_id: str
    tenant_id: str
    plan_id: str
    amount_usd: float
    currency: str = "usd"
    status: str = "draft"  # draft | open | paid | void
    period: str = ""
    created_at: float = 0.0
    paid_at: float = 0.0
    provider_ref: str = ""
    checkout_session_id: str = ""
    line_items: list[dict[str, Any]] = field(default_factory=list)

    def mark_paid(self, *, at: float, provider_ref: str = "") -> None:
        self.status = "paid"
        self.paid_at = at
        if provider_ref:
            self.provider_ref = provider_ref
