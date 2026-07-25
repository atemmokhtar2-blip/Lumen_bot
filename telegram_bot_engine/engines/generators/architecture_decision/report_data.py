"""
Architecture Decision Report data model (Specification 015).

This module defines the :class:`ArchitectureDecisionReport` -- the
complete, authoritative output of the
:class:`~telegram_bot_engine.engines.generators.architecture_decision.ArchitectureDecisionEngine`.

The Architecture Decision Engine is the engine responsible for making
ALL architectural decisions for the project.  It does not write code,
create files, build the project, or choose libraries.  Its sole
function is selecting the best architecture based on prior analysis
and producing the *Architecture Decision Report* -- the official
reference for all other engines.

Data sources
------------
The engine reads **five** data sources:

1. **Normalized Requirement Model** -- the
   ``requirement_normalization_report`` artefact produced by the
   :class:`~telegram_bot_engine.engines.generators.requirement_normalization.RequirementNormalizationEngine`.
2. **Project Intelligence Graph** -- the ``intelligence_graph``
   artefact produced by the
   :class:`~telegram_bot_engine.engines.generators.intelligence_graph.IntelligenceGraphEngine`.
3. **Requirement Intelligence Report** -- the
   ``requirement_intelligence_report`` artefact produced by the
   :class:`~telegram_bot_engine.engines.generators.requirement_intelligence.RequirementIntelligenceEngine`.
4. **Semantic Understanding Report** -- the
   ``semantic_understanding_report`` artefact produced by the
   :class:`~telegram_bot_engine.engines.generators.semantic_understanding.SemanticUnderstandingEngine`.
5. **Knowledge Base** -- the ``knowledge_base`` artefact, if
   present.

Design principles
------------------
* **Decisions, not code.**  The engine makes architectural decisions
  only.  It does not write code, create files, or build the project.
* **Analysis-driven.**  Every architectural decision is based on
  prior analysis (project size, scalability, performance, security,
  maintainability).
* **Decision validation.**  Every architectural decision must have a
  reason, an analysis, an impact, and rejected alternatives.
* **Scalability.**  The engine handles very large projects, not just
  small ones.  The architecture must scale.
* **Maintainability.**  The architecture must be clear, extensible,
  and maintainable.  Adding new features must not require rebuilding
  the architecture.
* **Quality gate.**  No architecture that fails quality or
  scalability requirements is allowed.
* **Traceability.**  Every decision records the data source it was
  derived from (``source_artefact``) so any downstream decision can
  trace its data back to the original source.
* **Caching.**  The engine caches the architecture decision so that
  it does not re-decide when the inputs have not changed.

The report is a plain data container -- no logic lives here.  The
engine and its helpers populate it; downstream consumers read it.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


# ---------------------------------------------------------------------------#
# Source-artefact constants
# ---------------------------------------------------------------------------#
#
# Every architectural decision records the data source it was derived
# from.  These constants are the stable identifiers for the five data
# sources.

SOURCE_NORMALIZED_REQUIREMENTS = "normalized_requirements"
SOURCE_INTELLIGENCE_GRAPH = "intelligence_graph"
SOURCE_REQUIREMENT_INTELLIGENCE = "requirement_intelligence"
SOURCE_SEMANTIC_UNDERSTANDING = "semantic_understanding"
SOURCE_KNOWLEDGE_BASE = "knowledge_base"

ALL_SOURCES = (
    SOURCE_NORMALIZED_REQUIREMENTS,
    SOURCE_INTELLIGENCE_GRAPH,
    SOURCE_REQUIREMENT_INTELLIGENCE,
    SOURCE_SEMANTIC_UNDERSTANDING,
    SOURCE_KNOWLEDGE_BASE,
)


# ---------------------------------------------------------------------------#
# Severity constants
# ---------------------------------------------------------------------------#

SEVERITY_ERROR = "error"
SEVERITY_WARNING = "warning"
SEVERITY_INFO = "info"

ALL_SEVERITIES = (SEVERITY_ERROR, SEVERITY_WARNING, SEVERITY_INFO)


# ---------------------------------------------------------------------------#
# Project size constants
# ---------------------------------------------------------------------------#
#
# The engine classifies the project into one of four size tiers.
# The size tier drives architecture decisions: a tiny project does
# not need a microservice architecture, and a very large project
# cannot use a monolith.

SIZE_TINY = "tiny"
SIZE_SMALL = "small"
SIZE_MEDIUM = "medium"
SIZE_LARGE = "large"
SIZE_VERY_LARGE = "very_large"

ALL_SIZES = (
    SIZE_TINY,
    SIZE_SMALL,
    SIZE_MEDIUM,
    SIZE_LARGE,
    SIZE_VERY_LARGE,
)

# Size thresholds (by requirement count).
SIZE_THRESHOLD_TINY = 5
SIZE_THRESHOLD_SMALL = 15
SIZE_THRESHOLD_MEDIUM = 50
SIZE_THRESHOLD_LARGE = 200


# ---------------------------------------------------------------------------#
# Architecture pattern constants
# ---------------------------------------------------------------------------#
#
# The architectural pattern selected for the project.

PATTERN_MONOLITH = "monolith"
PATTERN_LAYERED = "layered"
PATTERN_MODULAR_MONOLITH = "modular_monolith"
PATTERN_MICROSERVICES = "microservices"
PATTERN_EVENT_DRIVEN = "event_driven"
PATTERN_HEXAGONAL = "hexagonal"

ALL_PATTERNS = (
    PATTERN_MONOLITH,
    PATTERN_LAYERED,
    PATTERN_MODULAR_MONOLITH,
    PATTERN_MICROSERVICES,
    PATTERN_EVENT_DRIVEN,
    PATTERN_HEXAGONAL,
)

# Architecture pattern by size tier.
PATTERN_BY_SIZE: Dict[str, str] = {
    SIZE_TINY: PATTERN_MONOLITH,
    SIZE_SMALL: PATTERN_LAYERED,
    SIZE_MEDIUM: PATTERN_MODULAR_MONOLITH,
    SIZE_LARGE: PATTERN_LAYERED,
    SIZE_VERY_LARGE: PATTERN_MICROSERVICES,
}


# ---------------------------------------------------------------------------#
# Layer constants
# ---------------------------------------------------------------------------#
#
# The architectural layers.  The engine selects which layers the
# project needs.

LAYER_PRESENTATION = "presentation"
LAYER_BUSINESS = "business"
LAYER_DATA_ACCESS = "data_access"
LAYER_INFRASTRUCTURE = "infrastructure"
LAYER_INTEGRATION = "integration"
LAYER_CACHING = "caching"
LAYER_MESSAGING = "messaging"

ALL_LAYERS = (
    LAYER_PRESENTATION,
    LAYER_BUSINESS,
    LAYER_DATA_ACCESS,
    LAYER_INFRASTRUCTURE,
    LAYER_INTEGRATION,
    LAYER_CACHING,
    LAYER_MESSAGING,
)


# ---------------------------------------------------------------------------#
# Communication pattern constants
# ---------------------------------------------------------------------------#
#
# How the components and services communicate.

COMM_SYNC = "synchronous"
COMM_ASYNC = "asynchronous"
COMM_EVENT = "event_driven"
COMM_HYBRID = "hybrid"

ALL_COMM_PATTERNS = (COMM_SYNC, COMM_ASYNC, COMM_EVENT, COMM_HYBRID)


# ---------------------------------------------------------------------------#
# Error handling strategy constants
# ---------------------------------------------------------------------------#

ERROR_CENTRALIZED = "centralized"
ERROR_DISTRIBUTED = "distributed"
ERROR_LAYER_SPECIFIC = "layer_specific"
ERROR_RESULT_TYPE = "result_type"

ALL_ERROR_STRATEGIES = (
    ERROR_CENTRALIZED,
    ERROR_DISTRIBUTED,
    ERROR_LAYER_SPECIFIC,
    ERROR_RESULT_TYPE,
)


# ---------------------------------------------------------------------------#
# Configuration strategy constants
# ---------------------------------------------------------------------------#

CONFIG_STATIC = "static"
CONFIG_ENVIRONMENT = "environment"
CONFIG_FILE_BASED = "file_based"
CONFIG_HYBRID = "hybrid"

ALL_CONFIG_STRATEGIES = (
    CONFIG_STATIC,
    CONFIG_ENVIRONMENT,
    CONFIG_FILE_BASED,
    CONFIG_HYBRID,
)


# ---------------------------------------------------------------------------#
# Dependency structure constants
# ---------------------------------------------------------------------------#

DEP_FLAT = "flat"
DEP_LAYERED = "layered"
DEP_HIERARCHICAL = "hierarchical"
DEP_GRAPH = "graph"

ALL_DEP_STRUCTURES = (
    DEP_FLAT,
    DEP_LAYERED,
    DEP_HIERARCHICAL,
    DEP_GRAPH,
)


# ---------------------------------------------------------------------------#
# Project layout constants
# ---------------------------------------------------------------------------#

LAYOUT_FEATURE_BASED = "feature_based"
LAYOUT_LAYER_BASED = "layer_based"
LAYOUT_DOMAIN_BASED = "domain_based"
LAYOUT_HYBRID = "hybrid"

ALL_LAYOUTS = (
    LAYOUT_FEATURE_BASED,
    LAYOUT_LAYER_BASED,
    LAYOUT_DOMAIN_BASED,
    LAYOUT_HYBRID,
)


# ---------------------------------------------------------------------------#
# Analysis dimension constants
# ---------------------------------------------------------------------------#
#
# The five analysis dimensions the engine performs before making
# decisions.

DIMENSION_SIZE = "size"
DIMENSION_SCALABILITY = "scalability"
DIMENSION_PERFORMANCE = "performance"
DIMENSION_SECURITY = "security"
DIMENSION_MAINTAINABILITY = "maintainability"

ALL_DIMENSIONS = (
    DIMENSION_SIZE,
    DIMENSION_SCALABILITY,
    DIMENSION_PERFORMANCE,
    DIMENSION_SECURITY,
    DIMENSION_MAINTAINABILITY,
)


# ---------------------------------------------------------------------------#
# Decision domain constants
# ---------------------------------------------------------------------------#
#
# The eight decision domains the engine is responsible for.

DECISION_LAYERS = "layers"
DECISION_MODULES = "modules"
DECISION_SERVICES = "services"
DECISION_DEPENDENCY_STRUCTURE = "dependency_structure"
DECISION_PROJECT_LAYOUT = "project_layout"
DECISION_COMMUNICATION = "communication"
DECISION_ERROR_HANDLING = "error_handling"
DECISION_CONFIGURATION = "configuration"

ALL_DECISION_DOMAINS = (
    DECISION_LAYERS,
    DECISION_MODULES,
    DECISION_SERVICES,
    DECISION_DEPENDENCY_STRUCTURE,
    DECISION_PROJECT_LAYOUT,
    DECISION_COMMUNICATION,
    DECISION_ERROR_HANDLING,
    DECISION_CONFIGURATION,
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

    The engine performs five analyses (size, scalability,
    performance, security, maintainability).  This data class
    records the result of one analysis dimension.

    Attributes:
        dimension: The analysis dimension (one of the
            ``DIMENSION_*`` constants).
        score: 0.0-1.0 score for this dimension.
        level: The level (e.g. ``"tiny"``, ``"high"``,
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
    source_artefact: str = SOURCE_NORMALIZED_REQUIREMENTS

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
    """A rejected alternative for an architectural decision.

    Every architectural decision must record the alternatives that
    were considered and rejected.  This data class records a single
    rejected alternative.

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
# Architecture decision
# ---------------------------------------------------------------------------#

@dataclass
class ArchitectureDecision:
    """A single architectural decision.

    Every architectural decision must have a reason, an analysis,
    an impact, and a list of rejected alternatives.  This data class
    records a single decision.

    Attributes:
        domain: The decision domain (one of the
            ``DECISION_*`` constants).
        selected: The selected value (e.g. the selected
            pattern, the selected layers, the selected
            communication pattern).
        reason: The reason for this decision.
        analysis: The analysis that supports this decision.
        impact: The impact this decision will have.
        rejected_alternatives: The list of rejected
            alternatives.
        source_artefact: The artefact this decision was
            derived from.
        confidence: 0.0-1.0 confidence in this decision.
    """

    domain: str = ""
    selected: str = ""
    reason: str = ""
    analysis: str = ""
    impact: str = ""
    rejected_alternatives: List[RejectedAlternative] = field(
        default_factory=list
    )
    source_artefact: str = SOURCE_NORMALIZED_REQUIREMENTS
    confidence: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "domain": self.domain,
            "selected": self.selected,
            "reason": self.reason,
            "analysis": self.analysis,
            "impact": self.impact,
            "rejected_alternatives": [
                a.to_dict() for a in self.rejected_alternatives
            ],
            "source_artefact": self.source_artefact,
            "confidence": self.confidence,
        }


# ---------------------------------------------------------------------------#
# Architecture finding
# ---------------------------------------------------------------------------#

@dataclass
class ArchitectureFinding:
    """A general finding produced during architecture decision-making.

    Attributes:
        severity: ``"error"``, ``"warning"``, or ``"info"``.
        code: A short, machine-readable code.
        message: A human-readable description.
        affected: The name of the affected element.
        resolution_hint: An optional suggestion on how to fix
            the issue.
        category: The finding category.
    """

    severity: str = SEVERITY_WARNING
    code: str = ""
    message: str = ""
    affected: str = ""
    resolution_hint: str = ""
    category: str = "architecture"

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
    """Information about the cache for the architecture decision.

    Attributes:
        status: The cache status (one of the ``CACHE_*``
            constants).
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
# Architecture provenance
# ---------------------------------------------------------------------------#

@dataclass
class ArchitectureProvenance:
    """Records which data sources were used to build the Architecture
    Decision Report.

    Attributes:
        normalized_requirements_available: Whether the
            normalized requirement model was available.
        intelligence_graph_available: Whether the
            intelligence graph was available.
        requirement_intelligence_available: Whether the
            requirement intelligence report was available.
        semantic_understanding_available: Whether the
            semantic understanding report was available.
        knowledge_base_available: Whether the knowledge base
            was available.
        all_sources_used: The list of all source artefact
            identifiers that contributed to the report.
        requirement_count: The number of requirements from
            the normalized model.
        graph_node_count: The number of nodes in the
            intelligence graph.
        graph_edge_count: The number of edges in the
            intelligence graph.
        intent_kind: The intent kind from the semantic
            understanding report.
        semantic_confidence: The confidence from the
            semantic understanding report.
    """

    normalized_requirements_available: bool = False
    intelligence_graph_available: bool = False
    requirement_intelligence_available: bool = False
    semantic_understanding_available: bool = False
    knowledge_base_available: bool = False
    all_sources_used: List[str] = field(default_factory=list)
    requirement_count: int = 0
    graph_node_count: int = 0
    graph_edge_count: int = 0
    intent_kind: str = ""
    semantic_confidence: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "normalized_requirements_available":
                self.normalized_requirements_available,
            "intelligence_graph_available":
                self.intelligence_graph_available,
            "requirement_intelligence_available":
                self.requirement_intelligence_available,
            "semantic_understanding_available":
                self.semantic_understanding_available,
            "knowledge_base_available":
                self.knowledge_base_available,
            "all_sources_used": list(self.all_sources_used),
            "requirement_count": self.requirement_count,
            "graph_node_count": self.graph_node_count,
            "graph_edge_count": self.graph_edge_count,
            "intent_kind": self.intent_kind,
            "semantic_confidence": self.semantic_confidence,
        }


# ---------------------------------------------------------------------------#
# Module specification
# ---------------------------------------------------------------------------#

@dataclass
class ModuleSpec:
    """A module specification within the architecture.

    The engine selects the modules the project needs.  This data
    class records a single module.

    Attributes:
        name: The module name.
        layer: The layer this module belongs to.
        responsibility: The responsibility of this module.
        dependencies: The list of module names this module
            depends on.
    """

    name: str = ""
    layer: str = ""
    responsibility: str = ""
    dependencies: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "layer": self.layer,
            "responsibility": self.responsibility,
            "dependencies": list(self.dependencies),
        }


# ---------------------------------------------------------------------------#
# Service specification
# ---------------------------------------------------------------------------#

@dataclass
class ServiceSpec:
    """A service specification within the architecture.

    The engine selects the services the project needs.  This data
    class records a single service.

    Attributes:
        name: The service name.
        responsibility: The responsibility of this service.
        communication: How this service communicates
            (sync, async, event).
        dependencies: The list of service names this
            service depends on.
    """

    name: str = ""
    responsibility: str = ""
    communication: str = COMM_SYNC
    dependencies: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "responsibility": self.responsibility,
            "communication": self.communication,
            "dependencies": list(self.dependencies),
        }


# ---------------------------------------------------------------------------#
# The full Architecture Decision Report
# ---------------------------------------------------------------------------#

@dataclass
class ArchitectureDecisionReport:
    """The complete, authoritative output of the Architecture
    Decision Engine.

    This is the **only** object the engine produces.  It is stored
    in the generation context as the
    ``architecture_decision_report`` artefact and becomes the
    official reference for all other engines.

    The report contains:
    * The analysis results (size, scalability, performance,
      security, maintainability).
    * The architectural decisions (layers, modules, services,
      dependency structure, project layout, communication pattern,
      error handling strategy, configuration strategy).
    * The module specifications.
    * The service specifications.
    * The findings.
    * The cache info.
    * The provenance (traceability).
    * The confidence score and level.

    Attributes:
        analyses: The list of :class:`AnalysisResult` objects.
        decisions: The list of :class:`ArchitectureDecision`
            objects.
        modules: The list of :class:`ModuleSpec` objects.
        services: The list of :class:`ServiceSpec` objects.
        findings: The list of :class:`ArchitectureFinding`
            objects.
        cache_info: The :class:`CacheInfo`.
        provenance: The :class:`ArchitectureProvenance`.
        summary: A human-readable summary.
        notes: General notes about the report.
        warnings: Warnings produced during report building.
        confidence: 0.0-1.0 confidence in the architecture.
        confidence_level: The confidence level (one of the
            ``CONFIDENCE_*`` constants).
    """

    analyses: List[AnalysisResult] = field(default_factory=list)
    decisions: List[ArchitectureDecision] = field(default_factory=list)
    modules: List[ModuleSpec] = field(default_factory=list)
    services: List[ServiceSpec] = field(default_factory=list)
    findings: List[ArchitectureFinding] = field(default_factory=list)
    cache_info: CacheInfo = field(default_factory=CacheInfo)
    provenance: ArchitectureProvenance = field(
        default_factory=ArchitectureProvenance
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
    def decision_count(self) -> int:
        return len(self.decisions)

    @property
    def module_count(self) -> int:
        return len(self.modules)

    @property
    def service_count(self) -> int:
        return len(self.services)

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
        return self.decision_count == 0

    @property
    def has_sufficient_confidence(self) -> bool:
        """``True`` when the confidence is above the medium
        threshold."""
        return self.confidence >= CONFIDENCE_MEDIUM_THRESHOLD

    @property
    def all_decisions_validated(self) -> bool:
        """``True`` when every decision has a reason, an analysis,
        an impact, and at least one rejected alternative."""
        for decision in self.decisions:
            if not decision.reason:
                return False
            if not decision.analysis:
                return False
            if not decision.impact:
                return False
            if not decision.rejected_alternatives:
                return False
        return True if self.decision_count > 0 else False

    @property
    def ready(self) -> bool:
        """``True`` when the report is complete enough to proceed.

        The report is ready when:
        * There is at least one decision.
        * All decisions are validated (reason, analysis, impact,
          rejected alternatives).
        * There are no error-level findings.
        * The confidence is at or above the medium threshold.
        """
        return (
            self.decision_count > 0
            and self.all_decisions_validated
            and not self.has_errors
            and self.has_sufficient_confidence
        )

    @property
    def cache_hit(self) -> bool:
        return self.cache_info.hit

    # -- look-up helpers --------------------------------------------------#

    def get_decision(self, domain: str) -> Optional[ArchitectureDecision]:
        """Return the decision for the given domain, or ``None``."""
        for decision in self.decisions:
            if decision.domain == domain:
                return decision
        return None

    def get_analysis(self, dimension: str) -> Optional[AnalysisResult]:
        """Return the analysis for the given dimension, or ``None``."""
        for analysis in self.analyses:
            if analysis.dimension == dimension:
                return analysis
        return None

    def get_module(self, name: str) -> Optional[ModuleSpec]:
        """Return the module with the given name, or ``None``."""
        for module in self.modules:
            if module.name == name:
                return module
        return None

    def get_service(self, name: str) -> Optional[ServiceSpec]:
        """Return the service with the given name, or ``None``."""
        for service in self.services:
            if service.name == name:
                return service
        return None

    def decision_domains(self) -> List[str]:
        """Return the list of decision domains covered."""
        return [d.domain for d in self.decisions]

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
        category: str = "architecture",
    ) -> None:
        """Add a finding to the report."""
        self.findings.append(ArchitectureFinding(
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
            "decision_count": self.decision_count,
            "module_count": self.module_count,
            "service_count": self.service_count,
            "finding_count": self.finding_count,
            "error_count": self.error_count,
            "warning_count": self.warning_count,
            "has_errors": self.has_errors,
            "is_empty": self.is_empty,
            "all_decisions_validated": self.all_decisions_validated,
            "has_sufficient_confidence": self.has_sufficient_confidence,
            "ready": self.ready,
            "cache_hit": self.cache_hit,
            "confidence": self.confidence,
            "confidence_level": self.confidence_level,
            "summary": self.summary,
            "notes": list(self.notes),
            "warnings": list(self.warnings),
            "analyses": [a.to_dict() for a in self.analyses],
            "decisions": [d.to_dict() for d in self.decisions],
            "modules": [m.to_dict() for m in self.modules],
            "services": [s.to_dict() for s in self.services],
            "findings": [f.to_dict() for f in self.findings],
            "cache_info": self.cache_info.to_dict(),
            "provenance": self.provenance.to_dict(),
        }


__all__ = [
    # Source-artefact constants
    "SOURCE_NORMALIZED_REQUIREMENTS",
    "SOURCE_INTELLIGENCE_GRAPH",
    "SOURCE_REQUIREMENT_INTELLIGENCE",
    "SOURCE_SEMANTIC_UNDERSTANDING",
    "SOURCE_KNOWLEDGE_BASE",
    "ALL_SOURCES",
    # Severity constants
    "SEVERITY_ERROR",
    "SEVERITY_WARNING",
    "SEVERITY_INFO",
    "ALL_SEVERITIES",
    # Project size constants
    "SIZE_TINY",
    "SIZE_SMALL",
    "SIZE_MEDIUM",
    "SIZE_LARGE",
    "SIZE_VERY_LARGE",
    "ALL_SIZES",
    "SIZE_THRESHOLD_TINY",
    "SIZE_THRESHOLD_SMALL",
    "SIZE_THRESHOLD_MEDIUM",
    "SIZE_THRESHOLD_LARGE",
    # Architecture pattern constants
    "PATTERN_MONOLITH",
    "PATTERN_LAYERED",
    "PATTERN_MODULAR_MONOLITH",
    "PATTERN_MICROSERVICES",
    "PATTERN_EVENT_DRIVEN",
    "PATTERN_HEXAGONAL",
    "ALL_PATTERNS",
    "PATTERN_BY_SIZE",
    # Layer constants
    "LAYER_PRESENTATION",
    "LAYER_BUSINESS",
    "LAYER_DATA_ACCESS",
    "LAYER_INFRASTRUCTURE",
    "LAYER_INTEGRATION",
    "LAYER_CACHING",
    "LAYER_MESSAGING",
    "ALL_LAYERS",
    # Communication pattern constants
    "COMM_SYNC",
    "COMM_ASYNC",
    "COMM_EVENT",
    "COMM_HYBRID",
    "ALL_COMM_PATTERNS",
    # Error handling strategy constants
    "ERROR_CENTRALIZED",
    "ERROR_DISTRIBUTED",
    "ERROR_LAYER_SPECIFIC",
    "ERROR_RESULT_TYPE",
    "ALL_ERROR_STRATEGIES",
    # Configuration strategy constants
    "CONFIG_STATIC",
    "CONFIG_ENVIRONMENT",
    "CONFIG_FILE_BASED",
    "CONFIG_HYBRID",
    "ALL_CONFIG_STRATEGIES",
    # Dependency structure constants
    "DEP_FLAT",
    "DEP_LAYERED",
    "DEP_HIERARCHICAL",
    "DEP_GRAPH",
    "ALL_DEP_STRUCTURES",
    # Project layout constants
    "LAYOUT_FEATURE_BASED",
    "LAYOUT_LAYER_BASED",
    "LAYOUT_DOMAIN_BASED",
    "LAYOUT_HYBRID",
    "ALL_LAYOUTS",
    # Analysis dimension constants
    "DIMENSION_SIZE",
    "DIMENSION_SCALABILITY",
    "DIMENSION_PERFORMANCE",
    "DIMENSION_SECURITY",
    "DIMENSION_MAINTAINABILITY",
    "ALL_DIMENSIONS",
    # Decision domain constants
    "DECISION_LAYERS",
    "DECISION_MODULES",
    "DECISION_SERVICES",
    "DECISION_DEPENDENCY_STRUCTURE",
    "DECISION_PROJECT_LAYOUT",
    "DECISION_COMMUNICATION",
    "DECISION_ERROR_HANDLING",
    "DECISION_CONFIGURATION",
    "ALL_DECISION_DOMAINS",
    # Cache status constants
    "CACHE_HIT",
    "CACHE_MISS",
    "CACHE_STALE",
    "CACHE_DISABLED",
    "ALL_CACHE_STATUSES",
    # Confidence level constants
    "CONFIDENCE_HIGH",
    "CONFIDENCE_MEDIUM",
    "CONFIDENCE_LOW",
    "ALL_CONFIDENCE_LEVELS",
    "CONFIDENCE_HIGH_THRESHOLD",
    "CONFIDENCE_MEDIUM_THRESHOLD",
    # Data model
    "AnalysisResult",
    "RejectedAlternative",
    "ArchitectureDecision",
    "ArchitectureFinding",
    "CacheInfo",
    "ArchitectureProvenance",
    "ModuleSpec",
    "ServiceSpec",
    "ArchitectureDecisionReport",
]
