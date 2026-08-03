"""Tolerant data readers for Component Architecture Planning (Spec 022)."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from ....core.context import GenerationContext

_log = logging.getLogger("engine.component_architecture_planning.data_readers")


def _safe(artefact: Any) -> Dict[str, Any]:
    if hasattr(artefact, "to_dict"):
        return artefact.to_dict()
    if isinstance(artefact, dict):
        return artefact
    return {"value": str(artefact)}


@dataclass
class ModuleArchitectureData:
    available: bool = False
    modules: List[Dict[str, Any]] = field(default_factory=list)
    raw: Optional[Dict[str, Any]] = None
    error: str = ""


@dataclass
class ProjectStructureData:
    available: bool = False
    folders: List[Dict[str, Any]] = field(default_factory=list)
    files: List[Dict[str, Any]] = field(default_factory=list)
    raw: Optional[Dict[str, Any]] = None
    error: str = ""


@dataclass
class ExecutionPlanData:
    available: bool = False
    tasks: List[Dict[str, Any]] = field(default_factory=list)
    raw: Optional[Dict[str, Any]] = None
    error: str = ""


@dataclass
class ArchitectureDecisionData:
    available: bool = False
    architecture_style: str = ""
    components: List[Dict[str, Any]] = field(default_factory=list)
    raw: Optional[Dict[str, Any]] = None
    error: str = ""


@dataclass
class RequirementNormalizationData:
    available: bool = False
    features: List[Dict[str, Any]] = field(default_factory=list)
    raw: Optional[Dict[str, Any]] = None
    error: str = ""


class ModuleArchitectureReader:
    ARTEFACT_KEY = "module_architecture_blueprint"

    def read(self, context: GenerationContext) -> ModuleArchitectureData:
        data = ModuleArchitectureData()
        try:
            a = context.get(self.ARTEFACT_KEY)
            if a is None:
                data.error = f"Artefact '{self.ARTEFACT_KEY}' not found"
                return data
            raw = _safe(a)
            data.raw, data.available = raw, True
            data.modules = raw.get("modules") or []
        except Exception as exc:
            data.error = str(exc)
            _log.warning("ModuleArchitectureReader failed: %s", exc)
        return data


class ProjectStructureReader:
    ARTEFACT_KEY = "project_structure_blueprint"

    def read(self, context: GenerationContext) -> ProjectStructureData:
        data = ProjectStructureData()
        try:
            a = context.get(self.ARTEFACT_KEY)
            if a is None:
                data.error = f"Artefact '{self.ARTEFACT_KEY}' not found"
                return data
            raw = _safe(a)
            data.raw, data.available = raw, True
            data.folders = raw.get("folders") or []
            data.files = raw.get("files") or []
        except Exception as exc:
            data.error = str(exc)
        return data


class ExecutionPlanReader:
    ARTEFACT_KEY = "execution_plan"

    def read(self, context: GenerationContext) -> ExecutionPlanData:
        data = ExecutionPlanData()
        try:
            a = context.get(self.ARTEFACT_KEY)
            if a is None:
                data.error = f"Artefact '{self.ARTEFACT_KEY}' not found"
                return data
            raw = _safe(a)
            data.raw, data.available = raw, True
            data.tasks = raw.get("tasks") or []
        except Exception as exc:
            data.error = str(exc)
        return data


class ArchitectureDecisionReader:
    ARTEFACT_KEY = "architecture_decision_report"

    def read(self, context: GenerationContext) -> ArchitectureDecisionData:
        data = ArchitectureDecisionData()
        try:
            a = context.get(self.ARTEFACT_KEY)
            if a is None:
                data.error = f"Artefact '{self.ARTEFACT_KEY}' not found"
                return data
            raw = _safe(a)
            data.raw, data.available = raw, True
            data.architecture_style = raw.get("architecture_style") or raw.get("style") or ""
            data.components = raw.get("components") or []
        except Exception as exc:
            data.error = str(exc)
        return data


class RequirementNormalizationReader:
    ARTEFACT_KEY = "requirement_normalization_report"

    def read(self, context: GenerationContext) -> RequirementNormalizationData:
        data = RequirementNormalizationData()
        try:
            a = context.get(self.ARTEFACT_KEY)
            if a is None:
                data.error = f"Artefact '{self.ARTEFACT_KEY}' not found"
                return data
            raw = _safe(a)
            data.raw, data.available = raw, True
            data.features = raw.get("features") or []
        except Exception as exc:
            data.error = str(exc)
        return data


__all__ = [
    "ModuleArchitectureData",
    "ProjectStructureData",
    "ExecutionPlanData",
    "ArchitectureDecisionData",
    "RequirementNormalizationData",
    "ModuleArchitectureReader",
    "ProjectStructureReader",
    "ExecutionPlanReader",
    "ArchitectureDecisionReader",
    "RequirementNormalizationReader",
]
