"""Tolerant data readers for Repository Management (Spec 046)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from ....core.context import GenerationContext


def _safe(a: Any) -> Dict[str, Any]:
    if hasattr(a, "to_dict"):
        return a.to_dict()
    if isinstance(a, dict):
        return a
    return {"value": str(a)}


@dataclass
class GenericData:
    available: bool = False
    raw: Optional[Dict[str, Any]] = None
    items: List[Dict[str, Any]] = field(default_factory=list)
    error: str = ""


class _BaseReader:
    ARTEFACT_KEY = ""
    LIST_KEY = ""

    def read(self, ctx: GenerationContext) -> GenericData:
        d = GenericData()
        try:
            a = ctx.get(self.ARTEFACT_KEY)
            if a is None:
                d.error = f"missing {self.ARTEFACT_KEY}"
                return d
            raw = _safe(a)
            d.raw, d.available = raw, True
            if self.LIST_KEY:
                d.items = raw.get(self.LIST_KEY) or []
        except Exception as e:
            d.error = str(e)
        return d


class ProjectContextReader(_BaseReader):
    ARTEFACT_KEY = "project_context_report"
    LIST_KEY = "contexts"


class ProductionReadinessReader(_BaseReader):
    ARTEFACT_KEY = "production_readiness_report"
    LIST_KEY = "axes"


class UserRequestReader(_BaseReader):
    ARTEFACT_KEY = "user_request"
    LIST_KEY = "operations"

    def read(self, ctx: GenerationContext) -> GenericData:
        d = GenericData()
        try:
            a = ctx.get(self.ARTEFACT_KEY)
            if a is None:
                # Also try nested keys commonly used
                a = ctx.get("repository_request") or ctx.get("repo_request")
            if a is None:
                d.error = "missing user_request"
                return d
            raw = _safe(a)
            d.raw, d.available = raw, True
            ops = raw.get("operations") or raw.get("requested_operations") or []
            if isinstance(ops, list):
                d.items = ops
            elif ops:
                d.items = [ops]
        except Exception as e:
            d.error = str(e)
        return d


__all__ = [
    "GenericData",
    "ProjectContextReader",
    "ProductionReadinessReader",
    "UserRequestReader",
]
