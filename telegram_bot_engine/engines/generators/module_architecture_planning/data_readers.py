"""
Data readers for Module Architecture Planning Engine (Specification 021).
Tolerant readers that return available=False when artefacts are missing.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from ....core.context import GenerationContext

_log = logging.getLogger("engine.module_architecture_planning.data_readers")


@dataclass
class ExecutionPlanData:
    available: bool = False
    phases: List[Dict[str, Any]] = field(default_factory=list)
    tasks: List[Dict[str, Any]] = field(default_factory=list)
    raw: Optional[Dict[str, Any]] = None
    error: str = ""


@dataclass
class ProjectStructureData:
    available: bool = False
    folders: List[Dict[str, Any]] = field(default_factory=list)
    files: List[Dict[str, Any]] = field(default_factory=list)
    modules: List[Dict[str, Any]] = field(default_factory=list)
    raw: Optional[Dict[str, Any]] = None
    error: str = ""


@dataclass
class ArchitectureDecisionData:
    available: bool = False
    architecture_style: str = ""
    components: List[Dict[str, Any]] = field(default_factory=list)
    decisions: List[Dict[str, Any]] = field(default_factory=list)
    raw: Optional[Dict[str, Any]] = None
    error: str = ""


@dataclass
class RequirementNormalizationData:
    available: bool = False
    requirements: List[Dict[str, Any]] = field(default_factory=list)
    features: List[Dict[str, Any]] = field(default_factory=list)
    raw: Optional[Dict[str, Any]] = None
    error: str = ""


@dataclass
class TechnologySelectionData:
    available: bool = False
    language: str = ""
    framework: str = ""
    database: str = ""
    selected_technologies: List[Dict[str, Any]] = field(default_factory=list)
    raw: Optional[Dict[str, Any]] = None
    error: str = ""


def _safe_dict(artefact: Any) -> Dict[str, Any]:
    if hasattr(artefact, "to_dict"):
        return artefact.to_dict()
    if isinstance(artefact, dict):
        return artefact
    return {"value": str(artefact)}


class ExecutionPlanReader:
    ARTEFACT_KEY = "execution_plan"

    def read(self, context: GenerationContext) -> ExecutionPlanData:
        data = ExecutionPlanData()
        try:
            artefact = context.get(self.ARTEFACT_KEY)
            if artefact is None:
                data.error = f"Artefact '{self.ARTEFACT_KEY}' not found"
                return data
            raw = _safe_dict(artefact)
            data.raw, data.available = raw, True
            data.phases = raw.get("phases") or []
            data.tasks = raw.get("tasks") or []
        except Exception as exc:
            data.error = str(exc)
            _log.warning("ExecutionPlanReader failed: %s", exc)
        return data


class ProjectStructureReader:
    ARTEFACT_KEY = "project_structure_blueprint"

    def read(self, context: GenerationContext) -> ProjectStructureData:
        data = ProjectStructureData()
        try:
            artefact = context.get(self.ARTEFACT_KEY)
            if artefact is None:
                data.error = f"Artefact '{self.ARTEFACT_KEY}' not found"
                return data
            raw = _safe_dict(artefact)
            data.raw, data.available = raw, True
            data.folders = raw.get("folders") or []
            data.files = raw.get("files") or []
            data.modules = raw.get("modules") or []
        except Exception as exc:
            data.error = str(exc)
            _log.warning("ProjectStructureReader failed: %s", exc)
        return data


class ArchitectureDecisionReader:
    ARTEFACT_KEY = "architecture_decision_report"

    def read(self, context: GenerationContext) -> ArchitectureDecisionData:
        data = ArchitectureDecisionData()
        try:
            artefact = context.get(self.ARTEFACT_KEY)
            if artefact is None:
                data.error = f"Artefact '{self.ARTEFACT_KEY}' not found"
                return data
            raw = _safe_dict(artefact)
            data.raw, data.available = raw, True
            data.architecture_style = (
                raw.get("architecture_style") or raw.get("selected_style") or raw.get("style") or ""
            )
            data.components = raw.get("components") or []
            data.decisions = raw.get("decisions") or []
        except Exception as exc:
            data.error = str(exc)
            _log.warning("ArchitectureDecisionReader failed: %s", exc)
        return data


class RequirementNormalizationReader:
    ARTEFACT_KEY = "requirement_normalization_report"

    def read(self, context: GenerationContext) -> RequirementNormalizationData:
        data = RequirementNormalizationData()
        try:
            artefact = context.get(self.ARTEFACT_KEY)
            if artefact is None:
                data.error = f"Artefact '{self.ARTEFACT_KEY}' not found"
                return data
            raw = _safe_dict(artefact)
            data.raw, data.available = raw, True
            data.requirements = raw.get("requirements") or raw.get("normalized_requirements") or []
            data.features = raw.get("features") or []
        except Exception as exc:
            data.error = str(exc)
            _log.warning("RequirementNormalizationReader failed: %s", exc)
        return data


class TechnologySelectionReader:
    ARTEFACT_KEY = "technology_selection_report"

    def read(self, context: GenerationContext) -> TechnologySelectionData:
        data = TechnologySelectionData()
        try:
            artefact = context.get(self.ARTEFACT_KEY)
            if artefact is None:
                data.error = f"Artefact '{self.ARTEFACT_KEY}' not found"
                return data
            raw = _safe_dict(artefact)
            data.raw, data.available = raw, True
            data.language = raw.get("language") or "python"
            data.framework = raw.get("framework") or ""
            data.database = raw.get("database") or ""
            data.selected_technologies = raw.get("selected_technologies") or []
        except Exception as exc:
            data.error = str(exc)
            _log.warning("TechnologySelectionReader failed: %s", exc)
        return data


__all__ = [
    "ExecutionPlanData",
    "ProjectStructureData",
    "ArchitectureDecisionData",
    "RequirementNormalizationData",
    "TechnologySelectionData",
    "ExecutionPlanReader",
    "ProjectStructureReader",
    "ArchitectureDecisionReader",
    "RequirementNormalizationReader",
    "TechnologySelectionReader",
]
