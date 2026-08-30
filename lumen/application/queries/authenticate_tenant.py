from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class AuthenticateTenantQuery:
    api_key: str
