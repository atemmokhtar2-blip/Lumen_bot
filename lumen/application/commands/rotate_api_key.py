from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class RotateApiKeyCommand:
    tenant_id: str
