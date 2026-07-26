"""
Risk Analysis Report data model (Specification 018).

This module defines the :class:`RiskAnalysisReport` -- the complete,
authoritative output of the
:class:`~telegram_bot_engine.engines.generators.risk_detection.RiskDetectionEngine`.

The Risk Detection Engine is responsible for detecting **all
potential risks** before project generation begins.  It does **not**
write code, create files, or start the build process.  Its sole
function is to read the available design and architecture artefacts,
perform seven risk analyses, classify each risk by severity, produce
recommendations, and determine the project's readiness for the
generation phase.

Data sources
------------
The engine reads **five** data sources:

1. **Project Capability Report** -- the
   ``project_capability_report`` artefact produced by the
   :class:`~telegram_bot_engine.engines.generators.capability_analyzer.ProjectCapabilityAnalyzerEngine`.
2. **Architecture Decision Report** -- the
   ``architecture_decision_report`` artefact produced by the
   :class:`~telegram_bot_engine.engines.generators.architecture_decision.ArchitectureDecisionEngine`.
3. **Technology Selection Report** -- the
   ``technology_selection_report`` artefact produced by the
   :class:`~telegram_bot_engine.engines.generators.technology_selection.TechnologySelectionEngine`.
4. **Normalized Requirement Model** -- the
   ``requirement_normalization_report`` artefact produced by the
   :class:`~telegram_bot_engine.engines.generators.requirement_normalization.RequirementNormalizationEngine`.
5. **Knowledge Base** -- the ``knowledge_base`` artefact, if
   present.

Responsibilities
-----------------
* Perform **Architecture Risk Analysis** -- detect poor project
  partitioning, circular dependencies, excessive coupling, and
  weak extensibility.
* Perform **Performance Risk Analysis** -- detect potential
  bottlenecks, high memory consumption, slow operations, and
  unnecessary repetition.
* Perform **Scalability Risk Analysis** -- measure the design's
  ability to grow and identify weak points.
* Perform **Security Risk Analysis** -- analyze the design for
  potential security vulnerabilities before implementation.
* Perform **Dependency Risk Analysis** -- analyze all
  libraries/dependencies, detect conflicts or failure points.
* Perform **Maintenance Risk Analysis** -- detect risks to
  long-term maintainability.
* Perform **Resource Risk Analysis** -- detect risks related to
  resource consumption and availability.
* Classify each risk by **severity** -- Critical, High, Medium, or
  Low -- with reasoning.
* Produce **recommendations** for each risk -- cause, impact,
  suggested fix, and fix priority.
* Enforce **quality rules** -- if a Critical risk exists, do NOT
  allow transition to the generation phase before addressing it.

Output
------
The final output is a :class:`RiskAnalysisReport`, stored in the
context as the ``risk_analysis_report`` artefact.  The report
contains the risk list, severity scores, recommendations, and the
final project readiness status.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


# ---------------------------------------------------------------------------#
# Source-artefact constants
# ---------------------------------------------------------------------------#

SOURCE_PROJECT_CAPABILITY = "project_capability_report"
SOURCE_ARCHITECTURE_DECISION = "architecture_decision_report"
SOURCE_TECHNOLOGY_SELECTION = "technology_selection_report"
SOURCE_NORMALIZED_REQUIREMENTS = "requirement_normalization_report"
SOURCE_KNOWLEDGE_BASE = "knowledge_base"

ALL_SOURCES = (
    SOURCE_PROJECT_CAPABILITY,
    SOURCE_ARCHITECTURE_DECISION,
    SOURCE_TECHNOLOGY_SELECTION,
    SOURCE_NORMALIZED_REQUIREMENTS,
    SOURCE_KNOWLEDGE_BASE,
)


# ---------------------------------------------------------------------------#
# Risk severity constants
# ---------------------------------------------------------------------------#
#
# Each detected risk is classified into one of four severity
# levels.  Critical risks block the generation pipeline; all
# others are reported but do not block.

SEVERITY_CRITICAL = "critical"
SEVERITY_HIGH = "high"
SEVERITY_MEDIUM = "medium"
SEVERITY_LOW = "low"

ALL_SEVERITIES = (
    SEVERITY_CRITICAL,
    SEVERITY_HIGH,
    SEVERITY_MEDIUM,
    SEVERITY_LOW,
)

# Severity rank for comparison (higher = more severe).
SEVERITY_RANK = {
    SEVERITY_LOW: 1,
    SEVERITY_MEDIUM: 2,
    SEVERITY_HIGH: 3,
    SEVERITY_CRITICAL: 4,
}

# Severity scores (used for computing the overall risk score).
SEVERITY_SCORE = {
    SEVERITY_CRITICAL: 1.0,
    SEVERITY_HIGH: 0.75,
    SEVERITY_MEDIUM: 0.5,
    SEVERITY_LOW: 0.25,
}


# ---------------------------------------------------------------------------#
# Risk dimension constants
# ---------------------------------------------------------------------------#
#
# The seven risk analysis dimensions the engine performs.

DIMENSION_ARCHITECTURE = "architecture"
DIMENSION_PERFORMANCE = "performance"
DIMENSION_SCALABILITY = "scalability"
DIMENSION_SECURITY = "security"
DIMENSION_DEPENDENCY = "dependency"
DIMENSION_MAINTENANCE = "maintenance"
DIMENSION_RESOURCE = "resource"

ALL_DIMENSIONS = (
    DIMENSION_ARCHITECTURE,
    DIMENSION_PERFORMANCE,
    DIMENSION_SCALABILITY,
    DIMENSION_SECURITY,
    DIMENSION_DEPENDENCY,
    DIMENSION_MAINTENANCE,
    DIMENSION_RESOURCE,
)


# ---------------------------------------------------------------------------#
# Architecture risk type constants
# ---------------------------------------------------------------------------#

ARCH_RISK_POOR_PARTITIONING = "poor_partitioning"
ARCH_RISK_CIRCULAR_DEPENDENCIES = "circular_dependencies"
ARCH_RISK_EXCESSIVE_COUPLING = "excessive_coupling"
ARCH_RISK_WEAK_EXTENSIBILITY = "weak_extensibility"

ALL_ARCH_RISKS = (
    ARCH_RISK_POOR_PARTITIONING,
    ARCH_RISK_CIRCULAR_DEPENDENCIES,
    ARCH_RISK_EXCESSIVE_COUPLING,
    ARCH_RISK_WEAK_EXTENSIBILITY,
)


# ---------------------------------------------------------------------------#
# Performance risk type constants
# ---------------------------------------------------------------------------#

PERF_RISK_BOTTLENECK = "bottleneck"
PERF_RISK_HIGH_MEMORY = "high_memory_consumption"
PERF_RISK_SLOW_OPERATION = "slow_operation"
PERF_RISK_UNNECESSARY_REPETITION = "unnecessary_repetition"

ALL_PERF_RISKS = (
    PERF_RISK_BOTTLENECK,
    PERF_RISK_HIGH_MEMORY,
    PERF_RISK_SLOW_OPERATION,
    PERF_RISK_UNNECESSARY_REPETITION,
)


# ---------------------------------------------------------------------------#
# Security risk type constants
# ---------------------------------------------------------------------------#

SEC_RISK_INPUT_VALIDATION = "input_validation_missing"
SEC_RISK_AUTHORIZATION = "authorization_missing"
SEC_RISK_DATA_EXPOSURE = "data_exposure"
SEC_RISK_INSECURE_COMMUNICATION = "insecure_communication"
SEC_RISK_SECRETS_MANAGEMENT = "secrets_management"

ALL_SEC_RISKS = (
    SEC_RISK_INPUT_VALIDATION,
    SEC_RISK_AUTHORIZATION,
    SEC_RISK_DATA_EXPOSURE,
    SEC_RISK_INSECURE_COMMUNICATION,
    SEC_RISK_SECRETS_MANAGEMENT,
)


# ---------------------------------------------------------------------------#
# Dependency risk type constants
# ---------------------------------------------------------------------------#

DEP_RISK_VERSION_CONFLICT = "version_conflict"
DEP_RISK_DEPRECATED = "deprecated_library"
DEP_RISK_SECURITY_VULNERABILITY = "security_vulnerability"
DEP_RISK_TOO_MANY = "excessive_dependencies"
DEP_RISK_SINGLE_POINT = "single_point_of_failure"

ALL_DEP_RISKS = (
    DEP_RISK_VERSION_CONFLICT,
    DEP_RISK_DEPRECATED,
    DEP_RISK_SECURITY_VULNERABILITY,
    DEP_RISK_TOO_MANY,
    DEP_RISK_SINGLE_POINT,
)


# ---------------------------------------------------------------------------#
# Maintenance risk type constants
# ---------------------------------------------------------------------------#

MAINT_RISK_COMPLEXITY = "high_complexity"
MAINT_RISK_NO_TESTS = "no_test_strategy"
MAINT_RISK_NO_DOCS = "no_documentation"
MAINT_RISK_TIGHT_COUPLING = "tight_coupling"
MAINT_RISK_NO_MONITORING = "no_monitoring"

ALL_MAINT_RISKS = (
    MAINT_RISK_COMPLEXITY,
    MAINT_RISK_NO_TESTS,
    MAINT_RISK_NO_DOCS,
    MAINT_RISK_TIGHT_COUPLING,
    MAINT_RISK_NO_MONITORING,
)


# ---------------------------------------------------------------------------#
# Resource risk type constants
# ---------------------------------------------------------------------------#

RES_RISK_CPU_BOUND = "cpu_bound"
RES_RISK_MEMORY_BOUND = "memory_bound"
RES_RISK_DISK_BOUND = "disk_bound"
RES_RISK_NETWORK_BOUND = "network_bound"
RES_RISK_COST_OVERRUN = "cost_overrun"

ALL_RES_RISKS = (
    RES_RISK_CPU_BOUND,
    RES_RISK_MEMORY_BOUND,
    RES_RISK_DISK_BOUND,
    RES_RISK_NETWORK_BOUND,
    RES_RISK_COST_OVERRUN,
)


# ---------------------------------------------------------------------------#
# Fix priority constants
# ---------------------------------------------------------------------------#
#
# The priority for addressing each risk's recommendation.

PRIORITY_IMMEDIATE = "immediate"
PRIORITY_HIGH = "high"
PRIORITY_MEDIUM = "medium"
PRIORITY_LOW = "low"

ALL_PRIORITIES = (
    PRIORITY_IMMEDIATE,
    PRIORITY_HIGH,
    PRIORITY_MEDIUM,
    PRIORITY_LOW,
)


# ---------------------------------------------------------------------------#
# Quality rule constants
# ---------------------------------------------------------------------------#
#
# The quality rules the engine enforces.  If the critical-risk rule
# fails, the engine blocks the generation pipeline.

RULE_NO_CRITICAL_RISKS = "no_critical_risks"
RULE_ALL_DIMENSIONS_ANALYSED = "all_dimensions_analysed"
RULE_RISKS_HAVE_RECOMMENDATIONS = "risks_have_recommendations"
RULE_SUFFICIENT_CONFIDENCE = "sufficient_confidence"

ALL_QUALITY_RULES = (
    RULE_NO_CRITICAL_RISKS,
    RULE_ALL_DIMENSIONS_ANALYSED,
    RULE_RISKS_HAVE_RECOMMENDATIONS,
    RULE_SUFFICIENT_CONFIDENCE,
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
# Readiness verdict constants
# ---------------------------------------------------------------------------#
#
# The overall project readiness status determined by the engine.

VERDICT_READY = "ready"
VERDICT_READY_WITH_RISKS = "ready_with_risks"
VERDICT_NOT_READY = "not_ready"

ALL_VERDICTS = (VERDICT_READY, VERDICT_READY_WITH_RISKS, VERDICT_NOT_READY)


# ---------------------------------------------------------------------------#
# Risk Item
# ---------------------------------------------------------------------------#

@dataclass
class RiskItem:
    """A single detected risk.

    Each risk is classified by severity and dimension, and carries
    a full recommendation (cause, impact, suggested fix, fix
    priority).

    Attributes:
        risk_id: A unique, machine-readable risk identifier.
        dimension: The risk dimension (one of the
            ``DIMENSION_*`` constants).
        risk_type: The specific risk type within the dimension.
        severity: The severity (one of the ``SEVERITY_*``
            constants).
        title: A short, human-readable risk title.
        description: A detailed description of the risk.
        cause: The root cause of the risk.
        impact: The potential impact if the risk materialises.
        suggested_fix: A suggested fix or mitigation.
        fix_priority: The priority for addressing this risk (one
            of the ``PRIORITY_*`` constants).
        affected_components: The components or areas affected.
        reasoning: The reasoning behind the severity
            classification.
    """

    risk_id: str = ""
    dimension: str = ""
    risk_type: str = ""
    severity: str = SEVERITY_LOW
    title: str = ""
    description: str = ""
    cause: str = ""
    impact: str = ""
    suggested_fix: str = ""
    fix_priority: str = PRIORITY_LOW
    affected_components: List[str] = field(default_factory=list)
    reasoning: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "risk_id": self.risk_id,
            "dimension": self.dimension,
            "risk_type": self.risk_type,
            "severity": self.severity,
            "title": self.title,
            "description": self.description,
            "cause": self.cause,
            "impact": self.impact,
            "suggested_fix": self.suggested_fix,
            "fix_priority": self.fix_priority,
            "affected_components": list(self.affected_components),
            "reasoning": self.reasoning,
        }


# ---------------------------------------------------------------------------#
# Risk Recommendation
# ---------------------------------------------------------------------------#

@dataclass
class RiskRecommendation:
    """A recommendation for addressing a risk.

    While :class:`RiskItem` carries its own cause/impact/fix, the
    :class:`RiskRecommendation` provides a higher-level, actionable
    recommendation that may group multiple risks.

    Attributes:
        recommendation_id: A unique identifier.
        dimension: The dimension this recommendation addresses.
        priority: The fix priority (one of the ``PRIORITY_*``
            constants).
        title: A short title.
        description: A detailed description.
        related_risks: The risk IDs this recommendation addresses.
        expected_outcome: The expected outcome after applying the
            fix.
    """

    recommendation_id: str = ""
    dimension: str = ""
    priority: str = PRIORITY_LOW
    title: str = ""
    description: str = ""
    related_risks: List[str] = field(default_factory=list)
    expected_outcome: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "recommendation_id": self.recommendation_id,
            "dimension": self.dimension,
            "priority": self.priority,
            "title": self.title,
            "description": self.description,
            "related_risks": list(self.related_risks),
            "expected_outcome": self.expected_outcome,
        }


# ---------------------------------------------------------------------------#
# Risk Dimension Result
# ---------------------------------------------------------------------------#

@dataclass
class RiskDimensionResult:
    """The result of a single risk-dimension analysis.

    Attributes:
        dimension: The dimension (one of the ``DIMENSION_*``
            constants).
        risk_count: Number of risks detected in this dimension.
        critical_count: Number of critical risks.
        high_count: Number of high-severity risks.
        medium_count: Number of medium-severity risks.
        low_count: Number of low-severity risks.
        score: 0.0-1.0 risk score for this dimension (higher =
            more risky).
        summary: A human-readable summary.
        details: A list of detail strings.
        risks: The list of :class:`RiskItem` objects for this
            dimension.
    """

    dimension: str = ""
    risk_count: int = 0
    critical_count: int = 0
    high_count: int = 0
    medium_count: int = 0
    low_count: int = 0
    score: float = 0.0
    summary: str = ""
    details: List[str] = field(default_factory=list)
    risks: List[RiskItem] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "dimension": self.dimension,
            "risk_count": self.risk_count,
            "critical_count": self.critical_count,
            "high_count": self.high_count,
            "medium_count": self.medium_count,
            "low_count": self.low_count,
            "score": self.score,
            "summary": self.summary,
            "details": list(self.details),
            "risks": [r.to_dict() for r in self.risks],
        }


# ---------------------------------------------------------------------------#
# Risk Finding (general)
# ---------------------------------------------------------------------------#

@dataclass
class RiskFinding:
    """A general finding produced during risk analysis.

    Attributes:
        severity: ``"critical"``, ``"high"``, ``"medium"``, or
            ``"low"``.
        code: A short, machine-readable code.
        message: A human-readable description.
        affected: The name of the affected component or
            dimension.
        resolution_hint: An optional suggestion on how to fix
            the issue.
        category: The finding category.
    """

    severity: str = SEVERITY_LOW
    code: str = ""
    message: str = ""
    affected: str = ""
    resolution_hint: str = ""
    category: str = "risk"

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
# Cache Info
# ---------------------------------------------------------------------------#

@dataclass
class CacheInfo:
    """Information about the cache for the risk analysis report.

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
# Risk Provenance
# ---------------------------------------------------------------------------#

@dataclass
class RiskProvenance:
    """Records which data sources were used to build the Risk
    Analysis Report.

    Attributes:
        project_capability_available: Whether the project
            capability report was available.
        architecture_decision_available: Whether the
            architecture decision report was available.
        technology_selection_available: Whether the technology
            selection report was available.
        normalized_requirements_available: Whether the normalized
            requirement model was available.
        knowledge_base_available: Whether the knowledge base was
            available.
        all_sources_used: The list of all source artefact
            identifiers that contributed to the report.
        capability_verdict: The verdict from the capability
            report, if available.
        decision_count: The number of architectural decisions.
        selection_count: The number of technology selections.
        requirement_count: The number of normalized requirements.
    """

    project_capability_available: bool = False
    architecture_decision_available: bool = False
    technology_selection_available: bool = False
    normalized_requirements_available: bool = False
    knowledge_base_available: bool = False
    all_sources_used: List[str] = field(default_factory=list)
    capability_verdict: str = ""
    decision_count: int = 0
    selection_count: int = 0
    requirement_count: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "project_capability_available": (
                self.project_capability_available
            ),
            "architecture_decision_available": (
                self.architecture_decision_available
            ),
            "technology_selection_available": (
                self.technology_selection_available
            ),
            "normalized_requirements_available": (
                self.normalized_requirements_available
            ),
            "knowledge_base_available": (
                self.knowledge_base_available
            ),
            "all_sources_used": list(self.all_sources_used),
            "capability_verdict": self.capability_verdict,
            "decision_count": self.decision_count,
            "selection_count": self.selection_count,
            "requirement_count": self.requirement_count,
        }


# ---------------------------------------------------------------------------#
# The full Risk Analysis Report
# ---------------------------------------------------------------------------#

@dataclass
class RiskAnalysisReport:
    """The complete, authoritative output of the Risk Detection
    Engine.

    This is the **only** object the engine produces.  It is stored
    in the generation context as the ``risk_analysis_report``
    artefact and becomes the official reference for all downstream
    engines and the generation pipeline.

    The report contains:
    * The per-dimension risk results.
    * The complete risk list.
    * The severity scores.
    * The recommendations.
    * The strengths.
    * The findings.
    * The cache info.
    * The provenance (traceability).
    * The confidence score and level.
    * The overall project readiness status.

    Attributes:
        dimension_results: The per-dimension risk results.
        risks: The complete list of :class:`RiskItem` objects.
        recommendations: The list of
            :class:`RiskRecommendation` objects.
        findings: The list of :class:`RiskFinding` objects.
        strengths: The project's strengths.
        cache_info: The :class:`CacheInfo`.
        provenance: The :class:`RiskProvenance`.
        summary: A human-readable summary.
        notes: General notes about the report.
        warnings: Warnings produced during report building.
        confidence: 0.0-1.0 confidence in the analysis.
        confidence_level: The confidence level (one of the
            ``CONFIDENCE_*`` constants).
        verdict: The overall readiness verdict (one of the
            ``VERDICT_*`` constants).
    """

    dimension_results: List[RiskDimensionResult] = field(
        default_factory=list
    )
    risks: List[RiskItem] = field(default_factory=list)
    recommendations: List[RiskRecommendation] = field(
        default_factory=list
    )
    findings: List[RiskFinding] = field(default_factory=list)
    strengths: List[str] = field(default_factory=list)
    cache_info: CacheInfo = field(default_factory=CacheInfo)
    provenance: RiskProvenance = field(default_factory=RiskProvenance)
    summary: str = ""
    notes: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    confidence: float = 0.0
    confidence_level: str = CONFIDENCE_LOW
    verdict: str = VERDICT_NOT_READY

    # -- convenience -------------------------------------------------------#

    @property
    def dimension_count(self) -> int:
        """The number of dimensions analysed."""
        return len(self.dimension_results)

    @property
    def risk_count(self) -> int:
        """The total number of risks detected."""
        return len(self.risks)

    @property
    def recommendation_count(self) -> int:
        """The total number of recommendations."""
        return len(self.recommendations)

    @property
    def critical_count(self) -> int:
        """The number of critical-severity risks."""
        return sum(
            1 for r in self.risks if r.severity == SEVERITY_CRITICAL
        )

    @property
    def high_count(self) -> int:
        """The number of high-severity risks."""
        return sum(
            1 for r in self.risks if r.severity == SEVERITY_HIGH
        )

    @property
    def medium_count(self) -> int:
        """The number of medium-severity risks."""
        return sum(
            1 for r in self.risks if r.severity == SEVERITY_MEDIUM
        )

    @property
    def low_count(self) -> int:
        """The number of low-severity risks."""
        return sum(
            1 for r in self.risks if r.severity == SEVERITY_LOW
        )

    @property
    def has_critical_risks(self) -> bool:
        """True when at least one critical risk exists."""
        return self.critical_count > 0

    @property
    def all_dimensions_analysed(self) -> bool:
        """True when all seven dimensions have been analysed."""
        analysed = {d.dimension for d in self.dimension_results}
        return all(dim in analysed for dim in ALL_DIMENSIONS)

    @property
    def overall_risk_score(self) -> float:
        """The overall risk score (0.0-1.0, higher = more risky).

        Computed as the average of all risk severity scores,
        weighted by the number of risks at each level.  If no
        risks are detected, the score is 0.0 (no risk).
        """
        if not self.risks:
            return 0.0
        total = sum(
            SEVERITY_SCORE.get(r.severity, 0.0) for r in self.risks
        )
        return total / len(self.risks)

    @property
    def is_empty(self) -> bool:
        """True when no analysis has produced any result."""
        return (
            len(self.dimension_results) == 0
            and len(self.risks) == 0
        )

    @property
    def has_sufficient_confidence(self) -> bool:
        """True when the confidence is above the medium threshold."""
        return self.confidence >= CONFIDENCE_MEDIUM_THRESHOLD

    @property
    def is_ready(self) -> bool:
        """True when the verdict is READY or READY_WITH_RISKS."""
        return self.verdict in (VERDICT_READY, VERDICT_READY_WITH_RISKS)

    @property
    def is_blocked(self) -> bool:
        """True when the verdict is NOT_READY (generation blocked)."""
        return self.verdict == VERDICT_NOT_READY

    @property
    def ready(self) -> bool:
        """True when the report is complete enough to proceed.

        The report is ready when:
        * All seven dimensions have been analysed.
        * There are no critical risks.
        * The confidence is at or above the medium threshold.
        * The verdict is ready or ready with risks.
        """
        return (
            self.all_dimensions_analysed
            and not self.has_critical_risks
            and self.has_sufficient_confidence
            and self.is_ready
        )

    @property
    def cache_hit(self) -> bool:
        return self.cache_info.hit

    # -- look-up helpers --------------------------------------------------#

    def get_dimension(self, dimension: str) -> Optional[RiskDimensionResult]:
        """Return the dimension result for the given dimension, or
        None."""
        for dr in self.dimension_results:
            if dr.dimension == dimension:
                return dr
        return None

    def dimension_names(self) -> List[str]:
        """Return the list of dimension names analysed."""
        return [d.dimension for d in self.dimension_results]

    def risks_by_severity(self, severity: str) -> List[RiskItem]:
        """Return all risks with the given severity."""
        return [r for r in self.risks if r.severity == severity]

    def risks_by_dimension(self, dimension: str) -> List[RiskItem]:
        """Return all risks in the given dimension."""
        return [r for r in self.risks if r.dimension == dimension]

    def critical_risks(self) -> List[RiskItem]:
        """Return only the critical-severity risks."""
        return self.risks_by_severity(SEVERITY_CRITICAL)

    # -- risk management --------------------------------------------------#

    def add_risk(self, risk: RiskItem) -> None:
        """Add a risk to the report."""
        self.risks.append(risk)

    def add_recommendation(self, rec: RiskRecommendation) -> None:
        """Add a recommendation to the report."""
        self.recommendations.append(rec)

    def add_strength(self, strength: str) -> None:
        """Add a strength to the report."""
        self.strengths.append(strength)

    def add_finding(
        self,
        severity: str,
        code: str,
        message: str,
        affected: str = "",
        resolution_hint: str = "",
        category: str = "risk",
    ) -> None:
        """Add a finding to the report."""
        self.findings.append(RiskFinding(
            severity=severity,
            code=code,
            message=message,
            affected=affected,
            resolution_hint=resolution_hint,
            category=category,
        ))
        if severity in (SEVERITY_HIGH, SEVERITY_CRITICAL):
            self.warnings.append(message)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "dimension_count": self.dimension_count,
            "risk_count": self.risk_count,
            "recommendation_count": self.recommendation_count,
            "critical_count": self.critical_count,
            "high_count": self.high_count,
            "medium_count": self.medium_count,
            "low_count": self.low_count,
            "has_critical_risks": self.has_critical_risks,
            "all_dimensions_analysed": self.all_dimensions_analysed,
            "overall_risk_score": self.overall_risk_score,
            "is_empty": self.is_empty,
            "has_sufficient_confidence": self.has_sufficient_confidence,
            "is_ready": self.is_ready,
            "is_blocked": self.is_blocked,
            "ready": self.ready,
            "cache_hit": self.cache_hit,
            "confidence": self.confidence,
            "confidence_level": self.confidence_level,
            "verdict": self.verdict,
            "summary": self.summary,
            "notes": list(self.notes),
            "warnings": list(self.warnings),
            "strengths": list(self.strengths),
            "dimension_results": [
                d.to_dict() for d in self.dimension_results
            ],
            "risks": [r.to_dict() for r in self.risks],
            "recommendations": [
                r.to_dict() for r in self.recommendations
            ],
            "findings": [f.to_dict() for f in self.findings],
            "cache_info": self.cache_info.to_dict(),
            "provenance": self.provenance.to_dict(),
        }


__all__ = [
    # Data model -- sub-reports
    "RiskItem",
    "RiskRecommendation",
    "RiskDimensionResult",
    "RiskFinding",
    "CacheInfo",
    "RiskProvenance",
    "RiskAnalysisReport",
    # Source-artefact constants
    "SOURCE_PROJECT_CAPABILITY",
    "SOURCE_ARCHITECTURE_DECISION",
    "SOURCE_TECHNOLOGY_SELECTION",
    "SOURCE_NORMALIZED_REQUIREMENTS",
    "SOURCE_KNOWLEDGE_BASE",
    "ALL_SOURCES",
    # Severity constants
    "SEVERITY_CRITICAL",
    "SEVERITY_HIGH",
    "SEVERITY_MEDIUM",
    "SEVERITY_LOW",
    "ALL_SEVERITIES",
    "SEVERITY_RANK",
    "SEVERITY_SCORE",
    # Dimension constants
    "DIMENSION_ARCHITECTURE",
    "DIMENSION_PERFORMANCE",
    "DIMENSION_SCALABILITY",
    "DIMENSION_SECURITY",
    "DIMENSION_DEPENDENCY",
    "DIMENSION_MAINTENANCE",
    "DIMENSION_RESOURCE",
    "ALL_DIMENSIONS",
    # Architecture risk type constants
    "ARCH_RISK_POOR_PARTITIONING",
    "ARCH_RISK_CIRCULAR_DEPENDENCIES",
    "ARCH_RISK_EXCESSIVE_COUPLING",
    "ARCH_RISK_WEAK_EXTENSIBILITY",
    "ALL_ARCH_RISKS",
    # Performance risk type constants
    "PERF_RISK_BOTTLENECK",
    "PERF_RISK_HIGH_MEMORY",
    "PERF_RISK_SLOW_OPERATION",
    "PERF_RISK_UNNECESSARY_REPETITION",
    "ALL_PERF_RISKS",
    # Security risk type constants
    "SEC_RISK_INPUT_VALIDATION",
    "SEC_RISK_AUTHORIZATION",
    "SEC_RISK_DATA_EXPOSURE",
    "SEC_RISK_INSECURE_COMMUNICATION",
    "SEC_RISK_SECRETS_MANAGEMENT",
    "ALL_SEC_RISKS",
    # Dependency risk type constants
    "DEP_RISK_VERSION_CONFLICT",
    "DEP_RISK_DEPRECATED",
    "DEP_RISK_SECURITY_VULNERABILITY",
    "DEP_RISK_TOO_MANY",
    "DEP_RISK_SINGLE_POINT",
    "ALL_DEP_RISKS",
    # Maintenance risk type constants
    "MAINT_RISK_COMPLEXITY",
    "MAINT_RISK_NO_TESTS",
    "MAINT_RISK_NO_DOCS",
    "MAINT_RISK_TIGHT_COUPLING",
    "MAINT_RISK_NO_MONITORING",
    "ALL_MAINT_RISKS",
    # Resource risk type constants
    "RES_RISK_CPU_BOUND",
    "RES_RISK_MEMORY_BOUND",
    "RES_RISK_DISK_BOUND",
    "RES_RISK_NETWORK_BOUND",
    "RES_RISK_COST_OVERRUN",
    "ALL_RES_RISKS",
    # Fix priority constants
    "PRIORITY_IMMEDIATE",
    "PRIORITY_HIGH",
    "PRIORITY_MEDIUM",
    "PRIORITY_LOW",
    "ALL_PRIORITIES",
    # Quality rule constants
    "RULE_NO_CRITICAL_RISKS",
    "RULE_ALL_DIMENSIONS_ANALYSED",
    "RULE_RISKS_HAVE_RECOMMENDATIONS",
    "RULE_SUFFICIENT_CONFIDENCE",
    "ALL_QUALITY_RULES",
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
    # Verdict constants
    "VERDICT_READY",
    "VERDICT_READY_WITH_RISKS",
    "VERDICT_NOT_READY",
    "ALL_VERDICTS",
]
