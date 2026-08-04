"""Tolerant data readers for E2E Scenario Testing (Spec 044)."""

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


class UnitTestReader(_BaseReader):
    ARTEFACT_KEY = "unit_test_generation_report"
    LIST_KEY = "tests"


class IntegrationReader(_BaseReader):
    ARTEFACT_KEY = "integration_verification_report"
    LIST_KEY = "checks"


class RuntimeReader(_BaseReader):
    ARTEFACT_KEY = "runtime_simulation_report"
    LIST_KEY = "events"


class ArchitectureReader(_BaseReader):
    ARTEFACT_KEY = "architecture_compliance_report"
    LIST_KEY = "violations"


class SelfHealingReader(_BaseReader):
    ARTEFACT_KEY = "self_healing_report"
    LIST_KEY = "issues"


class ProjectContextReader(_BaseReader):
    ARTEFACT_KEY = "project_context_report"
    LIST_KEY = "contexts"


__all__ = [
    "GenericData",
    "UnitTestReader",
    "IntegrationReader",
    "RuntimeReader",
    "ArchitectureReader",
    "SelfHealingReader",
    "ProjectContextReader",
]
