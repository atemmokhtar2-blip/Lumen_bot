from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class CreateTenantCommand:
    name: str
    plan_id: str = "free"
    owner_telegram_id: int = 0
    brand_name: str = ""
    brand_logo_url: str = ""
    primary_color: str = "#2563eb"
    support_email: str = ""
    custom_domain: str = ""
