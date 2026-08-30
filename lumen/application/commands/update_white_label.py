from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class UpdateWhiteLabelCommand:
    tenant_id: str
    brand_name: str | None = None
    brand_logo_url: str | None = None
    primary_color: str | None = None
    support_email: str | None = None
    custom_domain: str | None = None
    name: str | None = None
