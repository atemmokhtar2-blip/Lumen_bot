"""
Data readers for the Execution Planning Engine (Specification 019).

Each reader is *tolerant*: if the upstream artefact is missing or
malformed it returns a lightweight ``*Data`` object with
``available=False`` instead of raising.  This allows the pipeline
to continue gracefully and still produce a best-effort plan.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from ....core.context import GenerationContext

_log = logging.getLogger("engine.execution_planning.data_readers")


# ---------------------------------------------------------------------------#
# Data containers
# ---------------------------------------------------------------------------#

@dataclass
class RequirementNormalizationData:
    """Wrapper around the Normalized Requirement Model."""

    available: bool = False
    requirements: List[Dict[str, Any]] = field(default_factory=list)
    features: List[Dict[str, Any]] = field(default_factory=list)
    raw: Optional[Dict[str, Any]] = None
    error: str = ""


@dataclass
class ArchitectureDecisionData:
    """Wrapper around the Architecture Decision Report."""

    available: bool = False
    decisions: List[Dict[str, Any]] = field(default_factory=list)
    architecture_style: str = ""
    components: List[Dict[str, Any]] = field(default_factory=list)
    raw: Optional[Dict[str, Any]] = None
    error: str = ""


@dataclass
class TechnologySelectionData:
    """Wrapper around the Technology Selection Report."""

    available: bool = False
    selected_technologies: List[Dict[str, Any]] = field(default_factory=list)
    language: str = ""
    framework: str = ""
    database: str = ""
    raw: Optional[Dict[str, Any]] = None
    error: str = ""


@dataclass
class RiskAnalysisData:
    """Wrapper around the Risk Analysis Report."""

    available: bool = False
    risks: List[Dict[str, Any]] = field(default_factory=list)
    critical_count: int = 0
    high_count: int = 0
    verdict: str = ""
    raw: Optional[Dict[str, Any]] = None
    error: str = ""


@dataclass
class ProjectCapabilityData:
    """Wrapper around the Project Capability Report."""

    available: bool = False
    capabilities: List[Dict[str, Any]] = field(default_factory=list)
    complexity_score: float = 0.0
    scalability_score: float = 0.0
    verdict: str = ""
    raw: Optional[Dict[str, Any]] = None
    error: str = ""


@dataclass
class KnowledgeData:
    """Wrapper around the Knowledge Base artefact."""

    available: bool = False
    entries: List[Dict[str, Any]] = field(default_factory=list)
    patterns: List[Dict[str, Any]] = field(default_factory=list)
    raw: Optional[Dict[str, Any]] = None
    error: str = ""


# ---------------------------------------------------------------------------#
# Readers
# ---------------------------------------------------------------------------#

class RequirementNormalizationReader:
    """Reads the Normalized Requirement Model from the context."""

    ARTEFACT_KEY = "requirement_normalization_report"

    def read(self, context: GenerationContext) -> RequirementNormalizationData:
        data = RequirementNormalizationData()
        try:
            artefact = context.get(self.ARTEFACT_KEY)
            if artefact is None:
                data.error = f"Artefact '{self.ARTEFACT_KEY}' not found"
                return data

            if hasattr(artefact, "to_dict"):
                raw = artefact.to_dict()
            elif isinstance(artefact, dict):
                raw = artefact
            else:
                raw = {"value": str(artefact)}

            data.raw = raw
            data.available = True

            # Extract common fields with defensive access.
            data.requirements = (
                raw.get("requirements")
                or raw.get("normalized_requirements")
                or raw.get("items")
                or []
            )
            data.features = (
                raw.get("features")
                or raw.get("feature_list")
                or []
            )
            if not isinstance(data.requirements, list):
                data.requirements = []
            if not isinstance(data.features, list):
                data.features = []

        except Exception as exc:
            _log.warning("RequirementNormalizationReader failed: %s", exc)
            data.error = str(exc)
            data.available = False

        return data


class ArchitectureDecisionReader:
    """Reads the Architecture Decision Report from the context."""

    ARTEFACT_KEY = "architecture_decision_report"

    def read(self, context: GenerationContext) -> ArchitectureDecisionData:
        data = ArchitectureDecisionData()
        try:
            artefact = context.get(self.ARTEFACT_KEY)
            if artefact is None:
                data.error = f"Artefact '{self.ARTEFACT_KEY}' not found"
                return data

            if hasattr(artefact, "to_dict"):
                raw = artefact.to_dict()
            elif isinstance(artefact, dict):
                raw = artefact
            else:
                raw = {"value": str(artefact)}

            data.raw = raw
            data.available = True
            data.decisions = raw.get("decisions") or raw.get("architecture_decisions") or []
            data.architecture_style = (
                raw.get("architecture_style")
                or raw.get("selected_style")
                or raw.get("style")
                or ""
            )
            data.components = raw.get("components") or raw.get("component_list") or []
            if not isinstance(data.decisions, list):
                data.decisions = []
            if not isinstance(data.components, list):
                data.components = []

        except Exception as exc:
            _log.warning("ArchitectureDecisionReader failed: %s", exc)
            data.error = str(exc)
            data.available = False

        return data


class TechnologySelectionReader:
    """Reads the Technology Selection Report from the context."""

    ARTEFACT_KEY = "technology_selection_report"

    def read(self, context: GenerationContext) -> TechnologySelectionData:
        data = TechnologySelectionData()
        try:
            artefact = context.get(self.ARTEFACT_KEY)
            if artefact is None:
                data.error = f"Artefact '{self.ARTEFACT_KEY}' not found"
                return data

            if hasattr(artefact, "to_dict"):
                raw = artefact.to_dict()
            elif isinstance(artefact, dict):
                raw = artefact
            else:
                raw = {"value": str(artefact)}

            data.raw = raw
            data.available = True
            data.selected_technologies = (
                raw.get("selected_technologies")
                or raw.get("technologies")
                or raw.get("selections")
                or []
            )
            data.language = raw.get("language") or raw.get("programming_language") or ""
            data.framework = raw.get("framework") or ""
            data.database = raw.get("database") or raw.get("db") or ""
            if not isinstance(data.selected_technologies, list):
                data.selected_technologies = []

        except Exception as exc:
            _log.warning("TechnologySelectionReader failed: %s", exc)
            data.error = str(exc)
            data.available = False

        return data


class RiskAnalysisReader:
    """Reads the Risk Analysis Report from the context."""

    ARTEFACT_KEY = "risk_analysis_report"

    def read(self, context: GenerationContext) -> RiskAnalysisData:
        data = RiskAnalysisData()
        try:
            artefact = context.get(self.ARTEFACT_KEY)
            if artefact is None:
                data.error = f"Artefact '{self.ARTEFACT_KEY}' not found"
                return data

            if hasattr(artefact, "to_dict"):
                raw = artefact.to_dict()
            elif isinstance(artefact, dict):
                raw = artefact
            else:
                raw = {"value": str(artefact)}

            data.raw = raw
            data.available = True
            data.risks = raw.get("risks") or raw.get("risk_list") or []
            data.critical_count = int(raw.get("critical_count") or 0)
            data.high_count = int(raw.get("high_count") or 0)
            data.verdict = raw.get("verdict") or raw.get("readiness_status") or ""
            if not isinstance(data.risks, list):
                data.risks = []

        except Exception as exc:
            _log.warning("RiskAnalysisReader failed: %s", exc)
            data.error = str(exc)
            data.available = False

        return data


class ProjectCapabilityReader:
    """Reads the Project Capability Report from the context."""

    ARTEFACT_KEY = "project_capability_report"

    def read(self, context: GenerationContext) -> ProjectCapabilityData:
        data = ProjectCapabilityData()
        try:
            artefact = context.get(self.ARTEFACT_KEY)
            if artefact is None:
                data.error = f"Artefact '{self.ARTEFACT_KEY}' not found"
                return data

            if hasattr(artefact, "to_dict"):
                raw = artefact.to_dict()
            elif isinstance(artefact, dict):
                raw = artefact
            else:
                raw = {"value": str(artefact)}

            data.raw = raw
            data.available = True
            data.capabilities = raw.get("capabilities") or raw.get("capability_list") or []
            data.complexity_score = float(raw.get("complexity_score") or raw.get("complexity") or 0.0)
            data.scalability_score = float(raw.get("scalability_score") or raw.get("scalability") or 0.0)
            data.verdict = raw.get("verdict") or ""
            if not isinstance(data.capabilities, list):
                data.capabilities = []

        except Exception as exc:
            _log.warning("ProjectCapabilityReader failed: %s", exc)
            data.error = str(exc)
            data.available = False

        return data


class KnowledgeReader:
    """Reads the Knowledge Base artefact from the context."""

    ARTEFACT_KEY = "knowledge_base"

    def read(self, context: GenerationContext) -> KnowledgeData:
        data = KnowledgeData()
        try:
            artefact = context.get(self.ARTEFACT_KEY)
            if artefact is None:
                data.error = f"Artefact '{self.ARTEFACT_KEY}' not found"
                return data

            if hasattr(artefact, "to_dict"):
                raw = artefact.to_dict()
            elif isinstance(artefact, dict):
                raw = artefact
            else:
                raw = {"value": str(artefact)}

            data.raw = raw
            data.available = True
            data.entries = raw.get("entries") or raw.get("items") or []
            data.patterns = raw.get("patterns") or raw.get("known_patterns") or []
            if not isinstance(data.entries, list):
                data.entries = []
            if not isinstance(data.patterns, list):
                data.patterns = []

        except Exception as exc:
            _log.warning("KnowledgeReader failed: %s", exc)
            data.error = str(exc)
            data.available = False

        return data


__all__ = [
    "RequirementNormalizationData",
    "ArchitectureDecisionData",
    "TechnologySelectionData",
    "RiskAnalysisData",
    "ProjectCapabilityData",
    "KnowledgeData",
    "RequirementNormalizationReader",
    "ArchitectureDecisionReader",
    "TechnologySelectionReader",
    "RiskAnalysisReader",
    "ProjectCapabilityReader",
    "KnowledgeReader",
]
