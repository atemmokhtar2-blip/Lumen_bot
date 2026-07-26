"""
Project Capability Report data model (Specification 017).

This module defines the :class:`ProjectCapabilityReport` -- the
complete, authoritative output of the
:class:`~telegram_bot_engine.engines.generators.capability_analyzer.ProjectCapabilityAnalyzerEngine`.

The Project Capability Analyzer is the engine responsible for
analysing the project's **full capability** before building starts.
It does **not** write code, create files, or build the project.
Its sole function is to measure whether the chosen architecture and
technologies can actually carry the project's demands -- complexity,
resources, scalability, stress, and dependencies -- and to block the
generation pipeline if they cannot.

Data sources
------------
The engine reads **five** data sources:

1. **Architecture Decision Report** -- the
   ``architecture_decision_report`` artefact produced by the
   :class:`~telegram_bot_engine.engines.generators.architecture_decision.ArchitectureDecisionEngine`.
2. **Technology Selection Report** -- the
   ``technology_selection_report`` artefact produced by the
   :class:`~telegram_bot_engine.engines.generators.technology_selection.TechnologySelectionEngine`.
3. **Normalized Requirement Model** -- the
   ``requirement_normalization_report`` artefact produced by the
   :class:`~telegram_bot_engine.engines.generators.requirement_normalization.RequirementNormalizationEngine`.
4. **Project Intelligence Graph** -- the ``intelligence_graph``
   artefact produced by the
   :class:`~telegram_bot_engine.engines.generators.intelligence_graph.IntelligenceGraphEngine`.
5. **Knowledge Base** -- the ``knowledge_base`` artefact, if present.

Responsibilities
----------------
* Perform **Complexity Analysis** -- measure the project's structural
  complexity (modules, services, components, classes, functions,
  interfaces, background tasks, external integrations).
* Perform **Resource Estimation** -- estimate the resources the
  project will consume (files, directories, project size, database
  size, memory, CPU, runtime resources).
* Perform **Scalability Analysis** -- check whether the architecture
  can support thousands, tens of thousands, hundreds of thousands,
  and millions of users.
* Perform **Architecture Stress Analysis** -- simulate high load,
  identify bottlenecks, sensitive components, and improvement points.
* Perform **Dependency Analysis** -- detect circular, unused, missing
  dependencies and dependency conflicts.
* Enforce **Quality Rules** -- block generation if the architecture
  cannot meet performance, scalability, or quality requirements.

Output
------
The final output is a :class:`ProjectCapabilityReport`, stored in
the context as the ``project_capability_report`` artefact.  The
report contains the complexity analysis, resource estimation,
scalability analysis, architecture stress analysis, dependency
analysis, strengths, potential risks, and recommendations.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


# ---------------------------------------------------------------------------#
# Source-artefact constants
# ---------------------------------------------------------------------------#

SOURCE_ARCHITECTURE_DECISION = "architecture_decision_report"
SOURCE_TECHNOLOGY_SELECTION = "technology_selection_report"
SOURCE_NORMALIZED_REQUIREMENTS = "normalized_requirements"
SOURCE_INTELLIGENCE_GRAPH = "intelligence_graph"
SOURCE_KNOWLEDGE_BASE = "knowledge_base"

ALL_SOURCES = (
    SOURCE_ARCHITECTURE_DECISION,
    SOURCE_TECHNOLOGY_SELECTION,
    SOURCE_NORMALIZED_REQUIREMENTS,
    SOURCE_INTELLIGENCE_GRAPH,
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
# Complexity level constants
# ---------------------------------------------------------------------------#

COMPLEXITY_TRIVIAL = "trivial"
COMPLEXITY_LOW = "low"
COMPLEXITY_MODERATE = "moderate"
COMPLEXITY_HIGH = "high"
COMPLEXITY_VERY_HIGH = "very_high"

ALL_COMPLEXITY_LEVELS = (
    COMPLEXITY_TRIVIAL,
    COMPLEXITY_LOW,
    COMPLEXITY_MODERATE,
    COMPLEXITY_HIGH,
    COMPLEXITY_VERY_HIGH,
)

# Complexity thresholds (by total element count).
COMPLEXITY_THRESHOLD_TRIVIAL = 5
COMPLEXITY_THRESHOLD_LOW = 15
COMPLEXITY_THRESHOLD_MODERATE = 40
COMPLEXITY_THRESHOLD_HIGH = 80


# ---------------------------------------------------------------------------#
# Project size constants
# ---------------------------------------------------------------------------#

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

# Size thresholds (by estimated file count).
SIZE_THRESHOLD_TINY = 20
SIZE_THRESHOLD_SMALL = 60
SIZE_THRESHOLD_MEDIUM = 150
SIZE_THRESHOLD_LARGE = 400


# ---------------------------------------------------------------------------#
# Scalability tier constants
# ---------------------------------------------------------------------------#
#
# The four scalability tiers the engine checks support for.

SCALE_THOUSANDS = "thousands"            # 1,000 - 9,999 users
SCALE_TENS_OF_THOUSANDS = "tens_of_thousands"  # 10,000 - 99,999
SCALE_HUNDREDS_OF_THOUSANDS = "hundreds_of_thousands"  # 100,000 - 999,999
SCALE_MILLIONS = "millions"             # 1,000,000+

ALL_SCALE_TIERS = (
    SCALE_THOUSANDS,
    SCALE_TENS_OF_THOUSANDS,
    SCALE_HUNDREDS_OF_THOUSANDS,
    SCALE_MILLIONS,
)

# User-count thresholds for each tier.
SCALE_THRESHOLD_THOUSANDS = 1_000
SCALE_THRESHOLD_TENS_OF_THOUSANDS = 10_000
SCALE_THRESHOLD_HUNDREDS_OF_THOUSANDS = 100_000
SCALE_THRESHOLD_MILLIONS = 1_000_000


# ---------------------------------------------------------------------------#
# Stress test load-level constants
# ---------------------------------------------------------------------------#

LOAD_LIGHT = "light"
LOAD_MODERATE = "moderate"
LOAD_HEAVY = "heavy"
LOAD_PEAK = "peak"

ALL_LOAD_LEVELS = (LOAD_LIGHT, LOAD_MODERATE, LOAD_HEAVY, LOAD_PEAK)


# ---------------------------------------------------------------------------#
# Bottleneck severity constants
# ---------------------------------------------------------------------------#

BOTTLENECK_CRITICAL = "critical"
BOTTLENECK_MAJOR = "major"
BOTTLENECK_MINOR = "minor"
BOTTLENECK_NONE = "none"

ALL_BOTTLENECK_LEVELS = (
    BOTTLENECK_CRITICAL,
    BOTTLENECK_MAJOR,
    BOTTLENECK_MINOR,
    BOTTLENECK_NONE,
)


# ---------------------------------------------------------------------------#
# Dependency issue type constants
# ---------------------------------------------------------------------------#

DEP_ISSUE_CIRCULAR = "circular_dependency"
DEP_ISSUE_UNUSED = "unused_dependency"
DEP_ISSUE_MISSING = "missing_dependency"
DEP_ISSUE_CONFLICT = "dependency_conflict"

ALL_DEP_ISSUES = (
    DEP_ISSUE_CIRCULAR,
    DEP_ISSUE_UNUSED,
    DEP_ISSUE_MISSING,
    DEP_ISSUE_CONFLICT,
)


# ---------------------------------------------------------------------------#
# Analysis dimension constants
# ---------------------------------------------------------------------------#
#
# The five analysis dimensions the engine performs.

DIMENSION_COMPLEXITY = "complexity"
DIMENSION_RESOURCES = "resources"
DIMENSION_SCALABILITY = "scalability"
DIMENSION_STRESS = "architecture_stress"
DIMENSION_DEPENDENCIES = "dependencies"

ALL_DIMENSIONS = (
    DIMENSION_COMPLEXITY,
    DIMENSION_RESOURCES,
    DIMENSION_SCALABILITY,
    DIMENSION_STRESS,
    DIMENSION_DEPENDENCIES,
)


# ---------------------------------------------------------------------------#
# Quality rule constants
# ---------------------------------------------------------------------------#
#
# The quality rules the engine enforces.  If any of these fail, the
# engine blocks the generation pipeline.

RULE_PERFORMANCE = "performance"
RULE_SCALABILITY = "scalability"
RULE_QUALITY = "quality"
RULE_DEPENDENCY_HEALTH = "dependency_health"

ALL_QUALITY_RULES = (
    RULE_PERFORMANCE,
    RULE_SCALABILITY,
    RULE_QUALITY,
    RULE_DEPENDENCY_HEALTH,
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
# Capability verdict constants
# ---------------------------------------------------------------------------#
#
# The overall verdict the engine reaches about the project's
# capability.

VERDICT_CAPABLE = "capable"
VERDICT_CAPABLE_WITH_RISKS = "capable_with_risks"
VERDICT_NOT_CAPABLE = "not_capable"

ALL_VERDICTS = (VERDICT_CAPABLE, VERDICT_CAPABLE_WITH_RISKS, VERDICT_NOT_CAPABLE)


# ---------------------------------------------------------------------------#
# Analysis result (per-dimension summary)
# ---------------------------------------------------------------------------#

@dataclass
class AnalysisResult:
    """The result of a single analysis dimension.

    The engine performs five analyses (complexity, resources,
    scalability, architecture stress, dependencies).  This data
    class records the result of one analysis dimension.

    Attributes:
        dimension: The analysis dimension (one of the
            ``DIMENSION_*`` constants).
        score: 0.0-1.0 score for this dimension.
        level: The level (e.g. ``"high"``, ``"moderate"``).
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
# Complexity Analysis
# ---------------------------------------------------------------------------#

@dataclass
class ComplexityAnalysis:
    """The complexity analysis of the project.

    Measures the project's structural complexity by counting the
    architectural elements: modules, services, components, classes,
    functions, interfaces, background tasks, and external integrations.

    Attributes:
        module_count: Number of modules.
        service_count: Number of services.
        component_count: Number of components.
        class_count: Estimated number of classes.
        function_count: Estimated number of functions.
        interface_count: Number of interfaces (API endpoints,
            message contracts).
        background_task_count: Number of background tasks /
            scheduled jobs.
        external_integration_count: Number of external
            integrations (third-party APIs, webhooks).
        total_elements: Total count of all elements.
        complexity_level: The overall complexity level (one of
            the ``COMPLEXITY_*`` constants).
        score: 0.0-1.0 complexity score (higher = more complex).
        summary: A human-readable summary.
        details: A list of detail strings.
    """

    module_count: int = 0
    service_count: int = 0
    component_count: int = 0
    class_count: int = 0
    function_count: int = 0
    interface_count: int = 0
    background_task_count: int = 0
    external_integration_count: int = 0
    total_elements: int = 0
    complexity_level: str = COMPLEXITY_TRIVIAL
    score: float = 0.0
    summary: str = ""
    details: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "module_count": self.module_count,
            "service_count": self.service_count,
            "component_count": self.component_count,
            "class_count": self.class_count,
            "function_count": self.function_count,
            "interface_count": self.interface_count,
            "background_task_count": self.background_task_count,
            "external_integration_count": self.external_integration_count,
            "total_elements": self.total_elements,
            "complexity_level": self.complexity_level,
            "score": self.score,
            "summary": self.summary,
            "details": list(self.details),
        }


# ---------------------------------------------------------------------------#
# Resource Estimation
# ---------------------------------------------------------------------------#

@dataclass
class ResourceEstimation:
    """The resource estimation for the project.

    Estimates the resources the project will consume: files,
    directories, total project size, database size, memory
    consumption, CPU consumption, and runtime resources.

    Attributes:
        file_count: Estimated number of files.
        directory_count: Estimated number of directories.
        project_size_kb: Estimated total project size in KB.
        database_size_mb: Estimated database size in MB.
        memory_mb: Estimated runtime memory consumption in MB.
        cpu_cores: Estimated CPU cores needed.
        estimated_build_time_minutes: Estimated build time.
        estimated_test_time_minutes: Estimated test time.
        project_size_level: The size level (one of the
            ``SIZE_*`` constants).
        score: 0.0-1.0 resource score (higher = more resources).
        summary: A human-readable summary.
        details: A list of detail strings.
    """

    file_count: int = 0
    directory_count: int = 0
    project_size_kb: int = 0
    database_size_mb: int = 0
    memory_mb: int = 0
    cpu_cores: float = 0.0
    estimated_build_time_minutes: float = 0.0
    estimated_test_time_minutes: float = 0.0
    project_size_level: str = SIZE_TINY
    score: float = 0.0
    summary: str = ""
    details: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "file_count": self.file_count,
            "directory_count": self.directory_count,
            "project_size_kb": self.project_size_kb,
            "database_size_mb": self.database_size_mb,
            "memory_mb": self.memory_mb,
            "cpu_cores": self.cpu_cores,
            "estimated_build_time_minutes":
                self.estimated_build_time_minutes,
            "estimated_test_time_minutes":
                self.estimated_test_time_minutes,
            "project_size_level": self.project_size_level,
            "score": self.score,
            "summary": self.summary,
            "details": list(self.details),
        }


# ---------------------------------------------------------------------------#
# Scalability Tier support
# ---------------------------------------------------------------------------#

@dataclass
class ScalabilityTier:
    """The capability of the architecture to support a given
    scalability tier.

    Attributes:
        tier: The scalability tier (one of the ``SCALE_*``
            constants).
        user_range: The user range for this tier.
        supported: Whether this tier is supported.
        confidence: 0.0-1.0 confidence that this tier is
            supported.
        reason: Why this tier is (or is not) supported.
        limitations: Known limitations at this tier.
    """

    tier: str = ""
    user_range: str = ""
    supported: bool = False
    confidence: float = 0.0
    reason: str = ""
    limitations: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "tier": self.tier,
            "user_range": self.user_range,
            "supported": self.supported,
            "confidence": self.confidence,
            "reason": self.reason,
            "limitations": list(self.limitations),
        }


# ---------------------------------------------------------------------------#
# Scalability Analysis
# ---------------------------------------------------------------------------#

@dataclass
class ScalabilityAnalysis:
    """The scalability analysis of the project.

    Checks whether the chosen architecture can support four
    scalability tiers: thousands, tens of thousands, hundreds of
    thousands, and millions of users.

    Attributes:
        tiers: A list of :class:`ScalabilityTier` objects, one
            per tier.
        max_supported_tier: The highest tier that is supported.
        score: 0.0-1.0 scalability score.
        summary: A human-readable summary.
        details: A list of detail strings.
    """

    tiers: List[ScalabilityTier] = field(default_factory=list)
    max_supported_tier: str = ""
    score: float = 0.0
    summary: str = ""
    details: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "tiers": [t.to_dict() for t in self.tiers],
            "max_supported_tier": self.max_supported_tier,
            "score": self.score,
            "summary": self.summary,
            "details": list(self.details),
        }

    def get_tier(self, tier: str) -> Optional[ScalabilityTier]:
        """Return the scalability tier with the given name, or None."""
        for t in self.tiers:
            if t.tier == tier:
                return t
        return None


# ---------------------------------------------------------------------------#
# Bottleneck
# ---------------------------------------------------------------------------#

@dataclass
class Bottleneck:
    """A bottleneck identified during architecture stress analysis.

    Attributes:
        component: The component or subsystem that is the
            bottleneck.
        severity: The bottleneck severity (one of the
            ``BOTTLENECK_*`` constants).
        load_level: The load level at which this bottleneck
            manifests (one of the ``LOAD_*`` constants).
        description: A human-readable description.
        impact: The impact this bottleneck has on the system.
        improvement: A suggested improvement.
    """

    component: str = ""
    severity: str = BOTTLENECK_MINOR
    load_level: str = LOAD_MODERATE
    description: str = ""
    impact: str = ""
    improvement: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "component": self.component,
            "severity": self.severity,
            "load_level": self.load_level,
            "description": self.description,
            "impact": self.impact,
            "improvement": self.improvement,
        }


# ---------------------------------------------------------------------------#
# Architecture Stress Analysis
# ---------------------------------------------------------------------------#

@dataclass
class ArchitectureStressAnalysis:
    """The architecture stress analysis of the project.

    Simulates high load on the architecture, identifies bottlenecks,
    sensitive components, and improvement points.

    Attributes:
        load_level: The maximum load level the architecture
            can sustain (one of the ``LOAD_*`` constants).
        bottlenecks: A list of :class:`Bottleneck` objects.
        sensitive_components: A list of sensitive component
            names.
        improvement_points: A list of suggested improvements.
        max_concurrent_users: Estimated max concurrent users.
        max_requests_per_second: Estimated max requests/sec.
        score: 0.0-1.0 stress score (higher = more robust).
        summary: A human-readable summary.
        details: A list of detail strings.
    """

    load_level: str = LOAD_LIGHT
    bottlenecks: List[Bottleneck] = field(default_factory=list)
    sensitive_components: List[str] = field(default_factory=list)
    improvement_points: List[str] = field(default_factory=list)
    max_concurrent_users: int = 0
    max_requests_per_second: float = 0.0
    score: float = 0.0
    summary: str = ""
    details: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "load_level": self.load_level,
            "bottlenecks": [b.to_dict() for b in self.bottlenecks],
            "sensitive_components": list(self.sensitive_components),
            "improvement_points": list(self.improvement_points),
            "max_concurrent_users": self.max_concurrent_users,
            "max_requests_per_second": self.max_requests_per_second,
            "score": self.score,
            "summary": self.summary,
            "details": list(self.details),
        }


# ---------------------------------------------------------------------------#
# Dependency Issue
# ---------------------------------------------------------------------------#

@dataclass
class DependencyIssue:
    """A dependency issue detected during dependency analysis.

    Attributes:
        issue_type: The issue type (one of the ``DEP_ISSUE_*``
            constants).
        component: The affected component.
        description: A human-readable description.
        severity: The severity (one of the ``SEVERITY_*``
            constants).
        resolution: A suggested resolution.
    """

    issue_type: str = DEP_ISSUE_UNUSED
    component: str = ""
    description: str = ""
    severity: str = SEVERITY_WARNING
    resolution: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "issue_type": self.issue_type,
            "component": self.component,
            "description": self.description,
            "severity": self.severity,
            "resolution": self.resolution,
        }


# ---------------------------------------------------------------------------#
# Dependency Analysis
# ---------------------------------------------------------------------------#

@dataclass
class DependencyAnalysis:
    """The dependency analysis of the project.

    Detects circular, unused, missing dependencies and dependency
    conflicts.

    Attributes:
        total_dependencies: Total number of dependencies.
        circular_dependencies: A list of circular dependency
            descriptions.
        unused_dependencies: A list of unused dependency
            descriptions.
        missing_dependencies: A list of missing dependency
            descriptions.
        conflicts: A list of dependency conflict descriptions.
        issues: A list of :class:`DependencyIssue` objects.
        is_healthy: Whether the dependency graph is healthy.
        score: 0.0-1.0 dependency health score.
        summary: A human-readable summary.
        details: A list of detail strings.
    """

    total_dependencies: int = 0
    circular_dependencies: List[str] = field(default_factory=list)
    unused_dependencies: List[str] = field(default_factory=list)
    missing_dependencies: List[str] = field(default_factory=list)
    conflicts: List[str] = field(default_factory=list)
    issues: List[DependencyIssue] = field(default_factory=list)
    is_healthy: bool = True
    score: float = 0.0
    summary: str = ""
    details: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "total_dependencies": self.total_dependencies,
            "circular_dependencies": list(self.circular_dependencies),
            "unused_dependencies": list(self.unused_dependencies),
            "missing_dependencies": list(self.missing_dependencies),
            "conflicts": list(self.conflicts),
            "issues": [i.to_dict() for i in self.issues],
            "is_healthy": self.is_healthy,
            "score": self.score,
            "summary": self.summary,
            "details": list(self.details),
        }


# ---------------------------------------------------------------------------#
# Capability finding
# ---------------------------------------------------------------------------#

@dataclass
class CapabilityFinding:
    """A general finding produced during capability analysis.

    Attributes:
        severity: ``"error"``, ``"warning"``, or ``"info"``.
        code: A short, machine-readable code.
        message: A human-readable description.
        affected: The name of the affected component or dimension.
        resolution_hint: An optional suggestion on how to fix
            the issue.
        category: The finding category.
    """

    severity: str = SEVERITY_WARNING
    code: str = ""
    message: str = ""
    affected: str = ""
    resolution_hint: str = ""
    category: str = "capability"

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
    """Information about the cache for the capability report.

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
# Capability provenance
# ---------------------------------------------------------------------------#

@dataclass
class CapabilityProvenance:
    """Records which data sources were used to build the Project
    Capability Report.

    Attributes:
        architecture_decision_available: Whether the architecture
            decision report was available.
        technology_selection_available: Whether the technology
            selection report was available.
        normalized_requirements_available: Whether the normalized
            requirement model was available.
        intelligence_graph_available: Whether the intelligence
            graph was available.
        knowledge_base_available: Whether the knowledge base was
            available.
        all_sources_used: The list of all source artefact
            identifiers that contributed to the report.
        decision_count: The number of architectural decisions
            available as input.
        selection_count: The number of technology selections
            available as input.
        requirement_count: The number of requirements from the
            normalized model.
        graph_node_count: The number of nodes in the intelligence
            graph.
        graph_edge_count: The number of edges in the intelligence
            graph.
    """

    architecture_decision_available: bool = False
    technology_selection_available: bool = False
    normalized_requirements_available: bool = False
    intelligence_graph_available: bool = False
    knowledge_base_available: bool = False
    all_sources_used: List[str] = field(default_factory=list)
    decision_count: int = 0
    selection_count: int = 0
    requirement_count: int = 0
    graph_node_count: int = 0
    graph_edge_count: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "architecture_decision_available":
                self.architecture_decision_available,
            "technology_selection_available":
                self.technology_selection_available,
            "normalized_requirements_available":
                self.normalized_requirements_available,
            "intelligence_graph_available":
                self.intelligence_graph_available,
            "knowledge_base_available":
                self.knowledge_base_available,
            "all_sources_used": list(self.all_sources_used),
            "decision_count": self.decision_count,
            "selection_count": self.selection_count,
            "requirement_count": self.requirement_count,
            "graph_node_count": self.graph_node_count,
            "graph_edge_count": self.graph_edge_count,
        }


# ---------------------------------------------------------------------------#
# The full Project Capability Report
# ---------------------------------------------------------------------------#

@dataclass
class ProjectCapabilityReport:
    """The complete, authoritative output of the Project Capability
    Analyzer Engine.

    This is the **only** object the engine produces.  It is stored in
    the generation context as the ``project_capability_report``
    artefact and becomes the official reference for all downstream
    engines that need capability information.

    The report contains:
    * The complexity analysis.
    * The resource estimation.
    * The scalability analysis.
    * The architecture stress analysis.
    * The dependency analysis.
    * The per-dimension analysis results.
    * The findings.
    * The strengths.
    * The potential risks.
    * The recommendations.
    * The cache info.
    * The provenance (traceability).
    * The confidence score and level.
    * The overall capability verdict.

    Attributes:
        complexity: The :class:`ComplexityAnalysis`.
        resources: The :class:`ResourceEstimation`.
        scalability: The :class:`ScalabilityAnalysis`.
        stress: The :class:`ArchitectureStressAnalysis`.
        dependencies: The :class:`DependencyAnalysis`.
        analyses: The list of :class:`AnalysisResult` objects.
        findings: The list of :class:`CapabilityFinding` objects.
        strengths: The project's strengths.
        risks: The project's potential risks.
        recommendations: The recommendations.
        cache_info: The :class:`CacheInfo`.
        provenance: The :class:`CapabilityProvenance`.
        summary: A human-readable summary.
        notes: General notes about the report.
        warnings: Warnings produced during report building.
        confidence: 0.0-1.0 confidence in the analysis.
        confidence_level: The confidence level (one of the
            ``CONFIDENCE_*`` constants).
        verdict: The overall capability verdict (one of the
            ``VERDICT_*`` constants).
    """

    complexity: ComplexityAnalysis = field(
        default_factory=ComplexityAnalysis
    )
    resources: ResourceEstimation = field(
        default_factory=ResourceEstimation
    )
    scalability: ScalabilityAnalysis = field(
        default_factory=ScalabilityAnalysis
    )
    stress: ArchitectureStressAnalysis = field(
        default_factory=ArchitectureStressAnalysis
    )
    dependencies: DependencyAnalysis = field(
        default_factory=DependencyAnalysis
    )
    analyses: List[AnalysisResult] = field(default_factory=list)
    findings: List[CapabilityFinding] = field(default_factory=list)
    strengths: List[str] = field(default_factory=list)
    risks: List[str] = field(default_factory=list)
    recommendations: List[str] = field(default_factory=list)
    cache_info: CacheInfo = field(default_factory=CacheInfo)
    provenance: CapabilityProvenance = field(
        default_factory=CapabilityProvenance
    )
    summary: str = ""
    notes: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    confidence: float = 0.0
    confidence_level: str = CONFIDENCE_LOW
    verdict: str = VERDICT_NOT_CAPABLE

    # -- convenience -------------------------------------------------------#

    @property
    def analysis_count(self) -> int:
        return len(self.analyses)

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
        """True when no analysis has produced any result."""
        return (
            self.complexity.total_elements == 0
            and self.resources.file_count == 0
            and len(self.scalability.tiers) == 0
            and len(self.stress.bottlenecks) == 0
            and self.dependencies.total_dependencies == 0
            and len(self.analyses) == 0
        )

    @property
    def has_sufficient_confidence(self) -> bool:
        """True when the confidence is above the medium threshold."""
        return self.confidence >= CONFIDENCE_MEDIUM_THRESHOLD

    @property
    def all_analyses_performed(self) -> bool:
        """True when all five analysis dimensions are present."""
        performed = {a.dimension for a in self.analyses}
        return all(d in performed for d in ALL_DIMENSIONS)

    @property
    def max_scalability_tier(self) -> str:
        """The highest scalability tier that is supported."""
        return self.scalability.max_supported_tier

    @property
    def is_capable(self) -> bool:
        """True when the verdict is CAPABLE or CAPABLE_WITH_RISKS."""
        return self.verdict in (VERDICT_CAPABLE, VERDICT_CAPABLE_WITH_RISKS)

    @property
    def is_blocked(self) -> bool:
        """True when the verdict is NOT_CAPABLE (generation blocked)."""
        return self.verdict == VERDICT_NOT_CAPABLE

    @property
    def ready(self) -> bool:
        """True when the report is complete enough to proceed.

        The report is ready when:
        * All five analyses have been performed.
        * There are no error-level findings.
        * The confidence is at or above the medium threshold.
        * The verdict is capable or capable with risks.
        """
        return (
            self.all_analyses_performed
            and not self.has_errors
            and self.has_sufficient_confidence
            and self.is_capable
        )

    @property
    def cache_hit(self) -> bool:
        return self.cache_info.hit

    # -- look-up helpers --------------------------------------------------#

    def get_analysis(self, dimension: str) -> Optional[AnalysisResult]:
        """Return the analysis for the given dimension, or None."""
        for analysis in self.analyses:
            if analysis.dimension == dimension:
                return analysis
        return None

    def analysis_dimensions(self) -> List[str]:
        """Return the list of analysis dimensions performed."""
        return [a.dimension for a in self.analyses]

    def get_scalability_tier(self, tier: str) -> Optional[ScalabilityTier]:
        """Return the scalability tier with the given name, or None."""
        return self.scalability.get_tier(tier)

    def critical_bottlenecks(self) -> List[Bottleneck]:
        """Return only the critical and major bottlenecks."""
        return [
            b for b in self.stress.bottlenecks
            if b.severity in (BOTTLENECK_CRITICAL, BOTTLENECK_MAJOR)
        ]

    # -- finding management -----------------------------------------------#

    def add_finding(
        self,
        severity: str,
        code: str,
        message: str,
        affected: str = "",
        resolution_hint: str = "",
        category: str = "capability",
    ) -> None:
        """Add a finding to the report."""
        self.findings.append(CapabilityFinding(
            severity=severity,
            code=code,
            message=message,
            affected=affected,
            resolution_hint=resolution_hint,
            category=category,
        ))
        if severity == SEVERITY_WARNING:
            self.warnings.append(message)

    def add_strength(self, strength: str) -> None:
        """Add a strength to the report."""
        self.strengths.append(strength)

    def add_risk(self, risk: str) -> None:
        """Add a risk to the report."""
        self.risks.append(risk)

    def add_recommendation(self, recommendation: str) -> None:
        """Add a recommendation to the report."""
        self.recommendations.append(recommendation)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "analysis_count": self.analysis_count,
            "finding_count": self.finding_count,
            "error_count": self.error_count,
            "warning_count": self.warning_count,
            "has_errors": self.has_errors,
            "is_empty": self.is_empty,
            "all_analyses_performed": self.all_analyses_performed,
            "has_sufficient_confidence": self.has_sufficient_confidence,
            "max_scalability_tier": self.max_scalability_tier,
            "is_capable": self.is_capable,
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
            "risks": list(self.risks),
            "recommendations": list(self.recommendations),
            "complexity": self.complexity.to_dict(),
            "resources": self.resources.to_dict(),
            "scalability": self.scalability.to_dict(),
            "stress": self.stress.to_dict(),
            "dependencies": self.dependencies.to_dict(),
            "analyses": [a.to_dict() for a in self.analyses],
            "findings": [f.to_dict() for f in self.findings],
            "cache_info": self.cache_info.to_dict(),
            "provenance": self.provenance.to_dict(),
        }


__all__ = [
    # Data model -- sub-reports
    "AnalysisResult",
    "ComplexityAnalysis",
    "ResourceEstimation",
    "ScalabilityTier",
    "ScalabilityAnalysis",
    "Bottleneck",
    "ArchitectureStressAnalysis",
    "DependencyIssue",
    "DependencyAnalysis",
    "CapabilityFinding",
    "CacheInfo",
    "CapabilityProvenance",
    "ProjectCapabilityReport",
    # Source-artefact constants
    "SOURCE_ARCHITECTURE_DECISION",
    "SOURCE_TECHNOLOGY_SELECTION",
    "SOURCE_NORMALIZED_REQUIREMENTS",
    "SOURCE_INTELLIGENCE_GRAPH",
    "SOURCE_KNOWLEDGE_BASE",
    "ALL_SOURCES",
    # Severity constants
    "SEVERITY_ERROR",
    "SEVERITY_WARNING",
    "SEVERITY_INFO",
    "ALL_SEVERITIES",
    # Complexity level constants
    "COMPLEXITY_TRIVIAL",
    "COMPLEXITY_LOW",
    "COMPLEXITY_MODERATE",
    "COMPLEXITY_HIGH",
    "COMPLEXITY_VERY_HIGH",
    "ALL_COMPLEXITY_LEVELS",
    "COMPLEXITY_THRESHOLD_TRIVIAL",
    "COMPLEXITY_THRESHOLD_LOW",
    "COMPLEXITY_THRESHOLD_MODERATE",
    "COMPLEXITY_THRESHOLD_HIGH",
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
    # Scalability tier constants
    "SCALE_THOUSANDS",
    "SCALE_TENS_OF_THOUSANDS",
    "SCALE_HUNDREDS_OF_THOUSANDS",
    "SCALE_MILLIONS",
    "ALL_SCALE_TIERS",
    "SCALE_THRESHOLD_THOUSANDS",
    "SCALE_THRESHOLD_TENS_OF_THOUSANDS",
    "SCALE_THRESHOLD_HUNDREDS_OF_THOUSANDS",
    "SCALE_THRESHOLD_MILLIONS",
    # Load level constants
    "LOAD_LIGHT",
    "LOAD_MODERATE",
    "LOAD_HEAVY",
    "LOAD_PEAK",
    "ALL_LOAD_LEVELS",
    # Bottleneck level constants
    "BOTTLENECK_CRITICAL",
    "BOTTLENECK_MAJOR",
    "BOTTLENECK_MINOR",
    "BOTTLENECK_NONE",
    "ALL_BOTTLENECK_LEVELS",
    # Dependency issue constants
    "DEP_ISSUE_CIRCULAR",
    "DEP_ISSUE_UNUSED",
    "DEP_ISSUE_MISSING",
    "DEP_ISSUE_CONFLICT",
    "ALL_DEP_ISSUES",
    # Analysis dimension constants
    "DIMENSION_COMPLEXITY",
    "DIMENSION_RESOURCES",
    "DIMENSION_SCALABILITY",
    "DIMENSION_STRESS",
    "DIMENSION_DEPENDENCIES",
    "ALL_DIMENSIONS",
    # Quality rule constants
    "RULE_PERFORMANCE",
    "RULE_SCALABILITY",
    "RULE_QUALITY",
    "RULE_DEPENDENCY_HEALTH",
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
    "VERDICT_CAPABLE",
    "VERDICT_CAPABLE_WITH_RISKS",
    "VERDICT_NOT_CAPABLE",
    "ALL_VERDICTS",
]
