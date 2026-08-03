"""Tolerant data readers for Generation Readiness Validation (Spec 027)."""

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
class BlueprintSnapshot:
    available: bool = False
    raw: Optional[Dict[str, Any]] = None
    verdict: str = ""
    is_empty: bool = True
    conflict_count: int = 0
    error: str = ""


class _BaseReader:
    ARTEFACT_KEY = ""

    def read(self, ctx: GenerationContext) -> BlueprintSnapshot:
        snap = BlueprintSnapshot()
        try:
            a = ctx.get(self.ARTEFACT_KEY)
            if a is None:
                snap.error = f"missing {self.ARTEFACT_KEY}"
                return snap
            raw = _safe(a)
            snap.raw = raw
            snap.available = True
            snap.verdict = (raw.get("verdict") or raw.get("readiness_status") or "").lower()
            snap.is_empty = bool(raw.get("is_empty", False))
            conflicts = raw.get("conflicts") or []
            snap.conflict_count = len(conflicts) if isinstance(conflicts, list) else 0
        except Exception as e:
            snap.error = str(e)
        return snap


class ExecutionPlanReader(_BaseReader):
    ARTEFACT_KEY = "execution_plan"


class ProjectStructureReader(_BaseReader):
    ARTEFACT_KEY = "project_structure_blueprint"


class ModuleArchitectureReader(_BaseReader):
    ARTEFACT_KEY = "module_architecture_blueprint"


class ComponentArchitectureReader(_BaseReader):
    ARTEFACT_KEY = "component_architecture_blueprint"


class InterfaceContractReader(_BaseReader):
    ARTEFACT_KEY = "interface_contract_blueprint"


class DataFlowReader(_BaseReader):
    ARTEFACT_KEY = "data_flow_blueprint"


class ResourceDependencyReader(_BaseReader):
    ARTEFACT_KEY = "resource_dependency_blueprint"


class GenerationStrategyReader(_BaseReader):
    ARTEFACT_KEY = "generation_strategy_blueprint"


__all__ = [
    "BlueprintSnapshot",
    "ExecutionPlanReader", "ProjectStructureReader", "ModuleArchitectureReader",
    "ComponentArchitectureReader", "InterfaceContractReader", "DataFlowReader",
    "ResourceDependencyReader", "GenerationStrategyReader",
]
