"""
Technology Selection Report data model (Specification 016).

This module defines the :class:`TechnologySelectionReport` -- the
complete, authoritative output of the
:class:`~telegram_bot_engine.engines.generators.technology_selection.TechnologySelectionEngine`.

The Technology Selection Engine is the engine responsible for selecting
all appropriate technologies for the project. It does not rely on fixed
lists or pre-built templates. It analyzes the project's needs and selects
the best-fit technologies accordingly.

Data sources
------------
The engine reads **five** data sources:

1. **Architecture Decision Report** -- the
   ``architecture_decision_report`` artefact produced by the
   :class:`~telegram_bot_engine.engines.generators.architecture_decision.ArchitectureDecisionEngine`.
2. **Normalized Requirement Model** -- the
   ``requirement_normalization_report`` artefact produced by the
   :class:`~telegram_bot_engine.engines.generators.requirement_normalization.RequirementNormalizationEngine`.
3. **Project Intelligence Graph** -- the ``intelligence_graph``
   artefact produced by the
   :class:`~telegram_bot_engine.engines.generators.intelligence_graph.IntelligenceGraphEngine`.
4. **Knowledge Base** -- the ``knowledge_base`` artefact, if present.
5. **Quality Rules** -- the ``quality_rules`` artefact, if present.

Responsibilities
----------------
* Select programming language, framework, database, ORM, cache,
  queue, storage, logging system, testing framework, and deployment
  requirements.
* Every choice must have a clear reason and alternatives must be
  compared.
* Select the best fit, not the most popular option.
* Perform compatibility, performance, security, and scalability
  analysis.
* Enforce quality rules: quality, stability, compatibility,
  scalability.

Output
------
The final output is an :class:`TechnologySelectionReport`, stored in
the context as the ``technology_selection_report`` artefact.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


# ---------------------------------------------------------------------------#
# Source-artefact constants
# ---------------------------------------------------------------------------#

SOURCE_ARCHITECTURE_DECISION = "architecture_decision_report"
SOURCE_NORMALIZED_REQUIREMENTS = "normalized_requirements"
SOURCE_INTELLIGENCE_GRAPH = "intelligence_graph"
SOURCE_KNOWLEDGE_BASE = "knowledge_base"
SOURCE_QUALITY_RULES = "quality_rules"

ALL_SOURCES = (
    SOURCE_ARCHITECTURE_DECISION,
    SOURCE_NORMALIZED_REQUIREMENTS,
    SOURCE_INTELLIGENCE_GRAPH,
    SOURCE_KNOWLEDGE_BASE,
    SOURCE_QUALITY_RULES,
)


# ---------------------------------------------------------------------------#
# Severity constants
# ---------------------------------------------------------------------------#

SEVERITY_ERROR = "error"
SEVERITY_WARNING = "warning"
SEVERITY_INFO = "info"

ALL_SEVERITIES = (SEVERITY_ERROR, SEVERITY_WARNING, SEVERITY_INFO)


# ---------------------------------------------------------------------------#
# Technology category constants
# ---------------------------------------------------------------------------#
#
# The ten technology categories the engine is responsible for selecting.

TECH_PROGRAMMING_LANGUAGE = "programming_language"
TECH_FRAMEWORK = "framework"
TECH_DATABASE = "database"
TECH_ORM = "orm"
TECH_CACHE = "cache"
TECH_QUEUE = "queue"
TECH_STORAGE = "storage"
TECH_LOGGING = "logging_system"
TECH_TESTING = "testing_framework"
TECH_DEPLOYMENT = "deployment_requirements"

ALL_TECH_CATEGORIES = (
    TECH_PROGRAMMING_LANGUAGE,
    TECH_FRAMEWORK,
    TECH_DATABASE,
    TECH_ORM,
    TECH_CACHE,
    TECH_QUEUE,
    TECH_STORAGE,
    TECH_LOGGING,
    TECH_TESTING,
    TECH_DEPLOYMENT,
)


# ---------------------------------------------------------------------------#
# Analysis dimension constants
# ---------------------------------------------------------------------------#
#
# The four analysis dimensions the engine performs before making
# technology selections.

DIMENSION_COMPATIBILITY = "compatibility"
DIMENSION_PERFORMANCE = "performance"
DIMENSION_SECURITY = "security"
DIMENSION_SCALABILITY = "future_scalability"

ALL_DIMENSIONS = (
    DIMENSION_COMPATIBILITY,
    DIMENSION_PERFORMANCE,
    DIMENSION_SECURITY,
    DIMENSION_SCALABILITY,
)


# ---------------------------------------------------------------------------#
# Quality rule constants
# ---------------------------------------------------------------------------#

RULE_QUALITY = "quality"
RULE_STABILITY = "stability"
RULE_COMPATIBILITY = "compatibility"
RULE_SCALABILITY = "scalability"

ALL_QUALITY_RULES = (
    RULE_QUALITY,
    RULE_STABILITY,
    RULE_COMPATIBILITY,
    RULE_SCALABILITY,
)


# ---------------------------------------------------------------------------#
# Cache status constants
# ---------------------------------------------------------------------------#

CACHE_HIT = "hit"
CACHE_MISS = "miss"
CACHE_STALE = "stale"
CACHE_DISABLED = "disabled"

ALL_CACHE_STATUSES = (CACHE_HIT, CACHE_MISS, CACHE_STALE, CACHE_DISABLED)


# ---------------------------------------------------------------------------#
# Confidence level constants
# ---------------------------------------------------------------------------#

CONFIDENCE_HIGH = "high"
CONFIDENCE_MEDIUM = "medium"
CONFIDENCE_LOW = "low"

ALL_CONFIDENCE_LEVELS = (CONFIDENCE_HIGH, CONFIDENCE_MEDIUM, CONFIDENCE_LOW)

CONFIDENCE_HIGH_THRESHOLD = 0.8
CONFIDENCE_MEDIUM_THRESHOLD = 0.6


# ---------------------------------------------------------------------------#
# Analysis result
# ---------------------------------------------------------------------------#

@dataclass
class AnalysisResult:
    """The result of a single analysis dimension.

    The engine performs four analyses (compatibility, performance,
    security, future scalability). This data class records the
    result of one analysis dimension.

    Attributes:
        dimension: The analysis dimension (one of the
            ``DIMENSION_*`` constants).
        score: 0.0-1.0 score for this dimension.
        level: The level (e.g. ``"high"``, ``"medium"``,
            ``"low"``).
        summary: A human-readable summary.
        details: A list of detail strings.
        source_artefact: The artefact this analysis was
            derived from.
    """

    dimension: str = ""
    score: float = 0.0
    level: str = ""
    summary: str = ""
    details: List[str] = field(default_factory=list)
    source_artefact: str = SOURCE_ARCHITECTURE_DECISION

    def to_dict(self) -> Dict[str, Any]:
        return {
            "dimension": self.dimension,
            "score": self.score,
            "level": self.level,
            "summary": self.summary,
            "details": list(self.details),
            "source_artefact": self.source_artefact,
        }


# ---------------------------------------------------------------------------#
# Rejected alternative
# ---------------------------------------------------------------------------#

@dataclass
class RejectedAlternative:
    """A rejected alternative for a technology selection.

    Every technology selection must record the alternatives that were
    considered and rejected. This data class records a single rejected
    alternative.

    Attributes:
        name: The name of the rejected alternative.
        reason: Why this alternative was rejected.
        impact: The impact this alternative would have had.
    """

    name: str = ""
    reason: str = ""
    impact: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "reason": self.reason,
            "impact": self.impact,
        }


# ---------------------------------------------------------------------------#
# Technology selection
# ---------------------------------------------------------------------------#

@dataclass
class TechnologySelection:
    """A single technology selection decision.

    Every technology selection must have a reason, an analysis,
    an impact, and a list of rejected alternatives. This data class
    records a single selection.

    Attributes:
        category: The technology category (one of the
            ``TECH_*`` constants).
        selected: The selected technology name.
        version: The recommended version (if known).
        reason: The reason for this selection.
        analysis: The analysis that supports this selection.
        impact: The impact this selection will have.
        pros: Advantages of this selection.
        cons: Disadvantages of this selection.
        rejected_alternatives: The list of rejected alternatives.
        source_artefact: The artefact this selection was
            derived from.
        confidence: 0.0-1.0 confidence in this selection.
    """

    category: str = ""
    selected: str = ""
    version: str = ""
    reason: str = ""
    analysis: str = ""
    impact: str = ""
    pros: List[str] = field(default_factory=list)
    cons: List[str] = field(default_factory=list)
    rejected_alternatives: List[RejectedAlternative] = field(
        default_factory=list
    )
    source_artefact: str = SOURCE_ARCHITECTURE_DECISION
    confidence: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "category": self.category,
            "selected": self.selected,
            "version": self.version,
            "reason": self.reason,
            "analysis": self.analysis,
            "impact": self.impact,
            "pros": list(self.pros),
            "cons": list(self.cons),
            "rejected_alternatives": [
                a.to_dict() for a in self.rejected_alternatives
            ],
            "source_artefact": self.source_artefact,
            "confidence": self.confidence,
        }


# ---------------------------------------------------------------------------#
# Technology finding
# ---------------------------------------------------------------------------#

@dataclass
class TechnologyFinding:
    """A general finding produced during technology selection.

    Attributes:
        severity: ``"error"``, ``"warning"``, or ``"info"``.
        code: A short, machine-readable code.
        message: A human-readable description.
        affected: The name of the affected technology or category.
        resolution_hint: An optional suggestion on how to fix
            the issue.
        category: The finding category.
    """

    severity: str = SEVERITY_WARNING
    code: str = ""
    message: str = ""
    affected: str = ""
    resolution_hint: str = ""
    category: str = "technology_selection"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "severity": self.severity,
            "code": self.code,
            "message": self.message,
            "affected": self.affected,
            "resolution_hint": self.resolution_hint,
            "category": self.category,
        }


# ---------------------------------------------------------------------------#
# Cache info
# ---------------------------------------------------------------------------#

@dataclass
class CacheInfo:
    """Information about the cache for the technology selection.

    Attributes:
        status: The cache status (one of the ``CACHE_*`` constants).
        cache_key: The key used for caching.
        cached_at: The timestamp when the cache was created.
        hit: Whether the cache was hit.
        inputs_hash: The hash of the input data sources.
    """

    status: str = CACHE_DISABLED
    cache_key: str = ""
    cached_at: str = ""
    hit: bool = False
    inputs_hash: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "status": self.status,
            "cache_key": self.cache_key,
            "cached_at": self.cached_at,
            "hit": self.hit,
            "inputs_hash": self.inputs_hash,
        }


# ---------------------------------------------------------------------------#
# Technology provenance
# ---------------------------------------------------------------------------#

@dataclass
class TechnologyProvenance:
    """Records which data sources were used to build the Technology
    Selection Report.

    Attributes:
        architecture_decision_available: Whether the architecture
            decision report was available.
        normalized_requirements_available: Whether the normalized
            requirement model was available.
        intelligence_graph_available: Whether the intelligence graph
            was available.
        knowledge_base_available: Whether the knowledge base was
            available.
        quality_rules_available: Whether the quality rules were
            available.
        all_sources_used: The list of all source artefact
            identifiers that contributed to the report.
        decision_count: The number of architectural decisions
            available as input.
        requirement_count: The number of requirements from the
            normalized model.
        graph_node_count: The number of nodes in the intelligence
            graph.
        graph_edge_count: The number of edges in the intelligence
            graph.
    """

    architecture_decision_available: bool = False
    normalized_requirements_available: bool = False
    intelligence_graph_available: bool = False
    knowledge_base_available: bool = False
    quality_rules_available: bool = False
    all_sources_used: List[str] = field(default_factory=list)
    decision_count: int = 0
    requirement_count: int = 0
    graph_node_count: int = 0
    graph_edge_count: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "architecture_decision_available":
                self.architecture_decision_available,
            "normalized_requirements_available":
                self.normalized_requirements_available,
            "intelligence_graph_available":
                self.intelligence_graph_available,
            "knowledge_base_available":
                self.knowledge_base_available,
            "quality_rules_available":
                self.quality_rules_available,
            "all_sources_used": list(self.all_sources_used),
            "decision_count": self.decision_count,
            "requirement_count": self.requirement_count,
            "graph_node_count": self.graph_node_count,
            "graph_edge_count": self.graph_edge_count,
        }


# ---------------------------------------------------------------------------#
# The full Technology Selection Report
# ---------------------------------------------------------------------------#

@dataclass
class TechnologySelectionReport:
    """The complete, authoritative output of the Technology Selection
    Engine.

    This is the **only** object the engine produces. It is stored in
    the generation context as the ``technology_selection_report``
    artefact and becomes the official reference for all downstream
    engines that need technology information.

    The report contains:
    * The analysis results (compatibility, performance, security,
      future scalability).
    * The technology selections (programming language, framework,
      database, ORM, cache, queue, storage, logging, testing,
      deployment).
    * The findings.
    * The cache info.
    * The provenance (traceability).
    * The confidence score and level.

    Attributes:
        analyses: The list of :class:`AnalysisResult` objects.
        selections: The list of :class:`TechnologySelection` objects.
        findings: The list of :class:`TechnologyFinding` objects.
        cache_info: The :class:`CacheInfo`.
        provenance: The :class:`TechnologyProvenance`.
        summary: A human-readable summary.
        notes: General notes about the report.
        warnings: Warnings produced during report building.
        confidence: 0.0-1.0 confidence in the selections.
        confidence_level: The confidence level (one of the
            ``CONFIDENCE_*`` constants).
    """

    analyses: List[AnalysisResult] = field(default_factory=list)
    selections: List[TechnologySelection] = field(default_factory=list)
    findings: List[TechnologyFinding] = field(default_factory=list)
    cache_info: CacheInfo = field(default_factory=CacheInfo)
    provenance: TechnologyProvenance = field(
        default_factory=TechnologyProvenance
    )
    summary: str = ""
    notes: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    confidence: float = 0.0
    confidence_level: str = CONFIDENCE_LOW

    # -- convenience -------------------------------------------------------#

    @property
    def analysis_count(self) -> int:
        return len(self.analyses)

    @property
    def selection_count(self) -> int:
        return len(self.selections)

    @property
    def finding_count(self) -> int:
        return len(self.findings)

    @property
    def error_count(self) -> int:
        return sum(
            1 for f in self.findings if f.severity == SEVERITY_ERROR
        )

    @property
    def warning_count(self) -> int:
        return sum(
            1 for f in self.findings if f.severity == SEVERITY_WARNING
        )

    @property
    def has_errors(self) -> bool:
        return self.error_count > 0

    @property
    def is_empty(self) -> bool:
        return self.selection_count == 0

    @property
    def has_sufficient_confidence(self) -> bool:
        """``True`` when the confidence is above the medium threshold."""
        return self.confidence >= CONFIDENCE_MEDIUM_THRESHOLD

    @property
    def all_selections_validated(self) -> bool:
        """``True`` when every selection has a reason, an analysis,
        an impact, and at least one rejected alternative."""
        for selection in self.selections:
            if not selection.reason:
                return False
            if not selection.analysis:
                return False
            if not selection.impact:
                return False
            if not selection.rejected_alternatives:
                return False
        return True if self.selection_count > 0 else False

    @property
    def ready(self) -> bool:
        """``True`` when the report is complete enough to proceed.

        The report is ready when:
        * There is at least one selection.
        * All selections are validated (reason, analysis, impact,
          rejected alternatives).
        * There are no error-level findings.
        * The confidence is at or above the medium threshold.
        """
        return (
            self.selection_count > 0
            and self.all_selections_validated
            and not self.has_errors
            and self.has_sufficient_confidence
        )

    @property
    def cache_hit(self) -> bool:
        return self.cache_info.hit

    # -- look-up helpers --------------------------------------------------#

    def get_selection(self, category: str) -> Optional[TechnologySelection]:
        """Return the selection for the given category, or ``None``."""
        for selection in self.selections:
            if selection.category == category:
                return selection
        return None

    def get_analysis(self, dimension: str) -> Optional[AnalysisResult]:
        """Return the analysis for the given dimension, or ``None``."""
        for analysis in self.analyses:
            if analysis.dimension == dimension:
                return analysis
        return None

    def selection_categories(self) -> List[str]:
        """Return the list of technology categories covered."""
        return [s.category for s in self.selections]

    def analysis_dimensions(self) -> List[str]:
        """Return the list of analysis dimensions performed."""
        return [a.dimension for a in self.analyses]

    # -- finding management -----------------------------------------------#

    def add_finding(
        self,
        severity: str,
        code: str,
        message: str,
        affected: str = "",
        resolution_hint: str = "",
        category: str = "technology_selection",
    ) -> None:
        """Add a finding to the report."""
        self.findings.append(TechnologyFinding(
            severity=severity,
            code=code,
            message=message,
            affected=affected,
            resolution_hint=resolution_hint,
            category=category,
        ))
        if severity == SEVERITY_WARNING:
            self.warnings.append(message)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "analysis_count": self.analysis_count,
            "selection_count": self.selection_count,
            "finding_count": self.finding_count,
            "error_count": self.error_count,
            "warning_count": self.warning_count,
            "has_errors": self.has_errors,
            "is_empty": self.is_empty,
            "all_selections_validated": self.all_selections_validated,
            "has_sufficient_confidence": self.has_sufficient_confidence,
            "ready": self.ready,
            "cache_hit": self.cache_hit,
            "confidence": self.confidence,
            "confidence_level": self.confidence_level,
            "summary": self.summary,
            "notes": list(self.notes),
            "warnings": list(self.warnings),
            "analyses": [a.to_dict() for a in self.analyses],
            "selections": [s.to_dict() for s in self.selections],
            "findings": [f.to_dict() for f in self.findings],
            "cache_info": self.cache_info.to_dict(),
            "provenance": self.provenance.to_dict(),
        }


__all__ = [
    "AnalysisResult",
    "RejectedAlternative",
    "TechnologySelection",
    "TechnologyFinding",
    "CacheInfo",
    "TechnologyProvenance",
    "TechnologySelectionReport",
    # Constants
    "SOURCE_ARCHITECTURE_DECISION",
    "SOURCE_NORMALIZED_REQUIREMENTS",
    "SOURCE_INTELLIGENCE_GRAPH",
    "SOURCE_KNOWLEDGE_BASE",
    "SOURCE_QUALITY_RULES",
    "ALL_SOURCES",
    "SEVERITY_ERROR",
    "SEVERITY_WARNING",
    "SEVERITY_INFO",
    "TECH_PROGRAMMING_LANGUAGE",
    "TECH_FRAMEWORK",
    "TECH_DATABASE",
    "TECH_ORM",
    "TECH_CACHE",
    "TECH_QUEUE",
    "TECH_STORAGE",
    "TECH_LOGGING",
    "TECH_TESTING",
    "TECH_DEPLOYMENT",
    "ALL_TECH_CATEGORIES",
    "DIMENSION_COMPATIBILITY",
    "DIMENSION_PERFORMANCE",
    "DIMENSION_SECURITY",
    "DIMENSION_SCALABILITY",
    "ALL_DIMENSIONS",
    "CONFIDENCE_HIGH",
    "CONFIDENCE_MEDIUM",
    "CONFIDENCE_LOW",
    "CONFIDENCE_HIGH_THRESHOLD",
    "CONFIDENCE_MEDIUM_THRESHOLD",
]
