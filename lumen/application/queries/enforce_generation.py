from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class EnforceGenerationQuery:
    tenant_id: str
    reserve: bool = True
