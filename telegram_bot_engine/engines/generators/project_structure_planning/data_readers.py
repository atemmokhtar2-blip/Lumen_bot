"""
Data readers for the Project Structure Planning Engine (Specification 020).

Each reader is *tolerant*: if the upstream artefact is missing or
malformed it returns a lightweight ``*Data`` object with
``available=False`` instead of raising.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from ....core.context import GenerationContext

_log = logging.getLogger("engine.project_structure_planning.data_readers")


@dataclass
class ExecutionPlanData:
    available: bool = False
    phases: List[Dict[str, Any]] = field(default_factory=list)
    tasks: List[Dict[str, Any]] = field(default_factory=list)
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
class TechnologySelectionData:
    available: bool = False
    language: str = ""
    framework: str = ""
    database: str = ""
    selected_technologies: List[Dict[str, Any]] = field(default_factory=list)
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
class ProjectCapabilityData:
    available: bool = False
    complexity_score: float = 0.0
    scalability_score: float = 0.0
    capabilities: List[Dict[str, Any]] = field(default_factory=list)
    raw: Optional[Dict[str, Any]] = None
    error: str = ""


class ExecutionPlanReader:
    ARTEFACT_KEY = "execution_plan"

    def read(self, context: GenerationContext) -> ExecutionPlanData:
        data = ExecutionPlanData()
        try:
            artefact = context.get(self.ARTEFACT_KEY)
            if artefact is None:
                data.error = f"Artefact '{self.ARTEFACT_KEY}' not found"
                return data
            raw = artefact.to_dict() if hasattr(artefact, "to_dict") else (
                artefact if isinstance(artefact, dict) else {"value": str(artefact)}
            )
            data.raw = raw
            data.available = True
            data.phases = raw.get("phases") or []
            data.tasks = raw.get("tasks") or []
            if not isinstance(data.phases, list):
                data.phases = []
            if not isinstance(data.tasks, list):
                data.tasks = []
        except Exception as exc:
            _log.warning("ExecutionPlanReader failed: %s", exc)
            data.error = str(exc)
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
            raw = artefact.to_dict() if hasattr(artefact, "to_dict") else (
                artefact if isinstance(artefact, dict) else {"value": str(artefact)}
            )
            data.raw = raw
            data.available = True
            data.architecture_style = (
                raw.get("architecture_style") or raw.get("selected_style") or raw.get("style") or ""
            )
            data.components = raw.get("components") or raw.get("component_list") or []
            data.decisions = raw.get("decisions") or raw.get("architecture_decisions") or []
            if not isinstance(data.components, list):
                data.components = []
            if not isinstance(data.decisions, list):
                data.decisions = []
        except Exception as exc:
            _log.warning("ArchitectureDecisionReader failed: %s", exc)
            data.error = str(exc)
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
            raw = artefact.to_dict() if hasattr(artefact, "to_dict") else (
                artefact if isinstance(artefact, dict) else {"value": str(artefact)}
            )
            data.raw = raw
            data.available = True
            data.language = raw.get("language") or raw.get("programming_language") or "python"
            data.framework = raw.get("framework") or ""
            data.database = raw.get("database") or raw.get("db") or ""
            data.selected_technologies = (
                raw.get("selected_technologies") or raw.get("technologies") or []
            )
            if not isinstance(data.selected_technologies, list):
                data.selected_technologies = []
        except Exception as exc:
            _log.warning("TechnologySelectionReader failed: %s", exc)
            data.error = str(exc)
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
            raw = artefact.to_dict() if hasattr(artefact, "to_dict") else (
                artefact if isinstance(artefact, dict) else {"value": str(artefact)}
            )
            data.raw = raw
            data.available = True
            data.requirements = raw.get("requirements") or raw.get("normalized_requirements") or []
            data.features = raw.get("features") or raw.get("feature_list") or []
            if not isinstance(data.requirements, list):
                data.requirements = []
            if not isinstance(data.features, list):
                data.features = []
        except Exception as exc:
            _log.warning("RequirementNormalizationReader failed: %s", exc)
            data.error = str(exc)
        return data


class ProjectCapabilityReader:
    ARTEFACT_KEY = "project_capability_report"

    def read(self, context: GenerationContext) -> ProjectCapabilityData:
        data = ProjectCapabilityData()
        try:
            artefact = context.get(self.ARTEFACT_KEY)
            if artefact is None:
                data.error = f"Artefact '{self.ARTEFACT_KEY}' not found"
                return data
            raw = artefact.to_dict() if hasattr(artefact, "to_dict") else (
                artefact if isinstance(artefact, dict) else {"value": str(artefact)}
            )
            data.raw = raw
            data.available = True
            data.complexity_score = float(raw.get("complexity_score") or raw.get("complexity") or 0.0)
            data.scalability_score = float(raw.get("scalability_score") or raw.get("scalability") or 0.0)
            data.capabilities = raw.get("capabilities") or raw.get("capability_list") or []
            if not isinstance(data.capabilities, list):
                data.capabilities = []
        except Exception as exc:
            _log.warning("ProjectCapabilityReader failed: %s", exc)
            data.error = str(exc)
        return data


__all__ = [
    "ExecutionPlanData",
    "ArchitectureDecisionData",
    "TechnologySelectionData",
    "RequirementNormalizationData",
    "ProjectCapabilityData",
    "ExecutionPlanReader",
    "ArchitectureDecisionReader",
    "TechnologySelectionReader",
    "RequirementNormalizationReader",
    "ProjectCapabilityReader",
]
