from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class EnforceApiQuery:
    tenant_id: str
