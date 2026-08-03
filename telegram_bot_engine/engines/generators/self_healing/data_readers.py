"""Tolerant data readers for Self-Healing (Spec 041)."""

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


class RuntimeReader(_BaseReader):
    ARTEFACT_KEY = "runtime_simulation_report"
    LIST_KEY = "events"


class StaticReader(_BaseReader):
    ARTEFACT_KEY = "static_analysis_report"
    LIST_KEY = "issues"


class ArchitectureReader(_BaseReader):
    ARTEFACT_KEY = "architecture_compliance_report"
    LIST_KEY = "violations"


class SecurityReader(_BaseReader):
    ARTEFACT_KEY = "security_review_report"
    LIST_KEY = "vulnerabilities"


class PerformanceReader(_BaseReader):
    ARTEFACT_KEY = "performance_optimization_report"
    LIST_KEY = "bottlenecks"


class RefactoringReader(_BaseReader):
    ARTEFACT_KEY = "code_refactoring_report"
    LIST_KEY = "smells"


__all__ = [
    "GenericData",
    "RuntimeReader",
    "StaticReader",
    "ArchitectureReader",
    "SecurityReader",
    "PerformanceReader",
    "RefactoringReader",
]
