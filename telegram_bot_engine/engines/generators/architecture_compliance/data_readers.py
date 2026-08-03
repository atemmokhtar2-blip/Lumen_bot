"""Tolerant data readers for Architecture Compliance (Spec 037)."""

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


class PerformanceReader(_BaseReader):
    ARTEFACT_KEY = "performance_optimization_report"
    LIST_KEY = "units"


class SecurityReader(_BaseReader):
    ARTEFACT_KEY = "security_review_report"
    LIST_KEY = "units"


class ArchitectureDecisionReader(_BaseReader):
    ARTEFACT_KEY = "architecture_decision_report"
    LIST_KEY = "decisions"


class ComponentArchitectureReader(_BaseReader):
    ARTEFACT_KEY = "component_architecture_blueprint"
    LIST_KEY = "components"


class InterfaceContractReader(_BaseReader):
    ARTEFACT_KEY = "interface_contract_blueprint"
    LIST_KEY = "interfaces"


class ModuleArchitectureReader(_BaseReader):
    ARTEFACT_KEY = "module_architecture_blueprint"
    LIST_KEY = "modules"


class ProjectContextReader(_BaseReader):
    ARTEFACT_KEY = "project_context_report"
    LIST_KEY = "contexts"


class BusinessLogicReader(_BaseReader):
    ARTEFACT_KEY = "business_logic_report"
    LIST_KEY = "bodies"


__all__ = [
    "GenericData",
    "PerformanceReader",
    "SecurityReader",
    "ArchitectureDecisionReader",
    "ComponentArchitectureReader",
    "InterfaceContractReader",
    "ModuleArchitectureReader",
    "ProjectContextReader",
    "BusinessLogicReader",
]
