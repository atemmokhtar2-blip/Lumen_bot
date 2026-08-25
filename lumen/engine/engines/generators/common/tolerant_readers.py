"""Shared tolerant artefact readers for generator engines (DRY)."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from ....core.context import GenerationContext


def safe_artefact(a: Any) -> Dict[str, Any]:
    if hasattr(a, "to_dict"):
        return a.to_dict()
    if isinstance(a, dict):
        return a
    return {"value": str(a)}


# Backward-compatible alias used by domain modules
_safe = safe_artefact


@dataclass
class GenericData:
    available: bool = False
    raw: Optional[Dict[str, Any]] = None
    items: List[Dict[str, Any]] = field(default_factory=list)
    error: str = ""


class BaseReader:
    """Read a GenerationContext artefact by key into GenericData."""

    ARTEFACT_KEY = ""
    LIST_KEY = ""

    def read(self, ctx: GenerationContext) -> GenericData:
        d = GenericData()
        try:
            a = ctx.get(self.ARTEFACT_KEY)
            if a is None:
                d.error = f"missing {self.ARTEFACT_KEY}"
                return d
            raw = safe_artefact(a)
            d.raw, d.available = raw, True
            if self.LIST_KEY:
                items = raw.get(self.LIST_KEY) or []
                d.items = items if isinstance(items, list) else [items]
        except Exception as e:
            d.error = str(e)
        return d


# Alias matching historical private name
_BaseReader = BaseReader

__all__ = [
    "GenericData",
    "BaseReader",
    "_BaseReader",
    "safe_artefact",
    "_safe",
]
