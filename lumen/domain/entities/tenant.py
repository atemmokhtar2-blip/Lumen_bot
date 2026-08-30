"""Tenant aggregate — identity + plan + white-label profile."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class Tenant:
    """B2B tenant (API customer). Pure domain — no persistence knowledge."""

    tenant_id: str
    name: str
    plan_id: str = "free"
    brand_name: str = ""
    brand_logo_url: str = ""
    primary_color: str = "#2563eb"
    support_email: str = ""
    custom_domain: str = ""
    api_key_hash: str = ""
    api_key_prefix: str = ""
    owner_telegram_id: int = 0
    active: bool = True
    created_at: float = 0.0
    metadata: dict[str, Any] = field(default_factory=dict)

    def ensure_active(self) -> None:
        if not self.active:
            raise PermissionError("tenant_inactive")

    def is_white_label(self) -> bool:
        return bool(self.brand_name or self.custom_domain)

    def public_dict(self) -> dict[str, Any]:
        return {
            "tenant_id": self.tenant_id,
            "name": self.name,
            "brand_name": self.brand_name or self.name,
            "brand_logo_url": self.brand_logo_url,
            "primary_color": self.primary_color,
            "support_email": self.support_email,
            "custom_domain": self.custom_domain,
            "api_key_prefix": self.api_key_prefix,
            "active": self.active,
            "created_at": self.created_at,
            "white_label": self.is_white_label(),
        }
