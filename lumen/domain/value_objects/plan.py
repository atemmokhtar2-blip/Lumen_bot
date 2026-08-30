"""Plan identifiers and tiers."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class PlanId:
    value: str

    def __post_init__(self) -> None:
        v = (self.value or "free").strip().lower()
        object.__setattr__(self, "value", v or "free")

    def __str__(self) -> str:
        return self.value


class PlanTier:
    FREE = "free"
    STARTER = "starter"
    GROWTH = "growth"
    BUSINESS = "business"
