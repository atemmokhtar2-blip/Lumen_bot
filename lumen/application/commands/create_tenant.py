from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class CreateTenantCommand:
    name: str
    plan_id: str = "free"
    owner_telegram_id: int = 0
