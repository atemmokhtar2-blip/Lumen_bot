"""Tolerant data readers for Resource & Dependency Planning (Spec 025)."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from ....core.context import GenerationContext

_log = logging.getLogger("engine.resource_dependency_planning.data_readers")


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


class ExecutionPlanReader(_BaseReader):
    ARTEFACT_KEY = "execution_plan"
    LIST_KEY = "tasks"


class ProjectStructureReader(_BaseReader):
    ARTEFACT_KEY = "project_structure_blueprint"
    LIST_KEY = "files"


class ModuleArchitectureReader(_BaseReader):
    ARTEFACT_KEY = "module_architecture_blueprint"
    LIST_KEY = "modules"


class ComponentArchitectureReader(_BaseReader):
    ARTEFACT_KEY = "component_architecture_blueprint"
    LIST_KEY = "components"


class InterfaceContractReader(_BaseReader):
    ARTEFACT_KEY = "interface_contract_blueprint"
    LIST_KEY = "interfaces"


class DataFlowReader(_BaseReader):
    ARTEFACT_KEY = "data_flow_blueprint"
    LIST_KEY = "sources"


class TechnologySelectionReader(_BaseReader):
    ARTEFACT_KEY = "technology_selection_report"
    LIST_KEY = "selected_technologies"


__all__ = [
    "GenericData",
    "ExecutionPlanReader", "ProjectStructureReader", "ModuleArchitectureReader",
    "ComponentArchitectureReader", "InterfaceContractReader", "DataFlowReader",
    "TechnologySelectionReader",
]
