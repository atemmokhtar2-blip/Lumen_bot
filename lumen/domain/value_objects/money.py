"""Money value object (USD-centric for current billing)."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Money:
    amount: float
    currency: str = "usd"

    def __post_init__(self) -> None:
        if self.amount < 0:
            raise ValueError("money_amount_negative")
        cur = (self.currency or "usd").strip().lower()
        object.__setattr__(self, "currency", cur)

    def add(self, other: "Money") -> "Money":
        if self.currency != other.currency:
            raise ValueError("currency_mismatch")
        return Money(self.amount + other.amount, self.currency)
