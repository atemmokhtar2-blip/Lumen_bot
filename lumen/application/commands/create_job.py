from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class CreateJobCommand:
    tenant_id: str
    kind: str
    input: dict[str, Any] = field(default_factory=dict)
