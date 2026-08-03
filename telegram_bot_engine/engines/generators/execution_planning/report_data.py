"""
Execution Plan data model (Specification 019).

This module defines the :class:`ExecutionPlan` -- the complete,
authoritative output of the
:class:`~telegram_bot_engine.engines.generators.execution_planning.ExecutionPlanningEngine`.

The Execution Planning Engine is responsible for converting all
previous analysis and planning artefacts into a precise, ordered
execution plan that the remaining engines of the system can follow
step by step.

The engine does **not** write code, create files, or modify the
project.  Its sole function is to produce the *Execution Plan* --
the official reference for all downstream engines that need to
know the correct order of operations.

Data sources
------------
The engine reads **six** data sources:

1. **Normalized Requirement Model** -- the
   ``requirement_normalization_report`` artefact produced by the
   :class:`~telegram_bot_engine.engines.generators.requirement_normalization.RequirementNormalizationEngine`.
2. **Architecture Decision Report** -- the
   ``architecture_decision_report`` artefact produced by the
   :class:`~telegram_bot_engine.engines.generators.architecture_decision.ArchitectureDecisionEngine`.
3. **Technology Selection Report** -- the
   ``technology_selection_report`` artefact produced by the
   :class:`~telegram_bot_engine.engines.generators.technology_selection.TechnologySelectionEngine`.
4. **Risk Analysis Report** -- the
   ``risk_analysis_report`` artefact produced by the
   :class:`~telegram_bot_engine.engines.generators.risk_detection.RiskDetectionEngine`.
5. **Project Capability Report** -- the
   ``project_capability_report`` artefact produced by the
   :class:`~telegram_bot_engine.engines.generators.capability_analyzer.ProjectCapabilityAnalyzerEngine`.
6. **Knowledge Base** -- the ``knowledge_base`` artefact, if present.

Responsibilities
-----------------
* Analyse the complete project from all upstream artefacts.
* Determine the correct execution order of every task.
* Partition the work into clear, sequential phases.
* Establish relationships and dependencies between phases.
* Prevent any conflict between tasks.
* Detect tasks that can safely run in parallel.
* Detect tasks that must run sequentially.
* Validate the final plan for completeness and consistency.
* Produce the *Execution Plan* with readiness status.

The plan is considered ready for the next stage only when it
passes every quality rule with a 100 % validity score.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple


# ---------------------------------------------------------------------------#
# Source constants
# ---------------------------------------------------------------------------#

SOURCE_NORMALIZED_REQUIREMENTS = "requirement_normalization_report"
SOURCE_ARCHITECTURE_DECISION = "architecture_decision_report"
SOURCE_TECHNOLOGY_SELECTION = "technology_selection_report"
SOURCE_RISK_ANALYSIS = "risk_analysis_report"
SOURCE_PROJECT_CAPABILITY = "project_capability_report"
SOURCE_KNOWLEDGE_BASE = "knowledge_base"

ALL_SOURCES = (
    SOURCE_NORMALIZED_REQUIREMENTS,
    SOURCE_ARCHITECTURE_DECISION,
    SOURCE_TECHNOLOGY_SELECTION,
    SOURCE_RISK_ANALYSIS,
    SOURCE_PROJECT_CAPABILITY,
    SOURCE_KNOWLEDGE_BASE,
)


# ---------------------------------------------------------------------------#
# Phase constants
# ---------------------------------------------------------------------------#

PHASE_FOUNDATION = "foundation"
PHASE_CORE_SYSTEM = "core_system"
PHASE_FEATURES = "features"
PHASE_INTEGRATIONS = "integrations"
PHASE_TESTING = "testing"
PHASE_OPTIMIZATION = "optimization"
PHASE_DEPLOYMENT_PREPARATION = "deployment_preparation"

ALL_PHASES = (
    PHASE_FOUNDATION,
    PHASE_CORE_SYSTEM,
    PHASE_FEATURES,
    PHASE_INTEGRATIONS,
    PHASE_TESTING,
    PHASE_OPTIMIZATION,
    PHASE_DEPLOYMENT_PREPARATION,
)

PHASE_ORDER = {
    PHASE_FOUNDATION: 10,
    PHASE_CORE_SYSTEM: 20,
    PHASE_FEATURES: 30,
    PHASE_INTEGRATIONS: 40,
    PHASE_TESTING: 50,
    PHASE_OPTIMIZATION: 60,
    PHASE_DEPLOYMENT_PREPARATION: 70,
}


# ---------------------------------------------------------------------------#
# Task status / execution mode constants
# ---------------------------------------------------------------------------#

TASK_STATUS_PENDING = "pending"
TASK_STATUS_READY = "ready"
TASK_STATUS_BLOCKED = "blocked"
TASK_STATUS_COMPLETED = "completed"

ALL_TASK_STATUSES = (
    TASK_STATUS_PENDING,
    TASK_STATUS_READY,
    TASK_STATUS_BLOCKED,
    TASK_STATUS_COMPLETED,
)

EXECUTION_MODE_SEQUENTIAL = "sequential"
EXECUTION_MODE_PARALLEL = "parallel"

ALL_EXECUTION_MODES = (
    EXECUTION_MODE_SEQUENTIAL,
    EXECUTION_MODE_PARALLEL,
)


# ---------------------------------------------------------------------------#
# Priority constants
# ---------------------------------------------------------------------------#

PRIORITY_CRITICAL = "critical"
PRIORITY_HIGH = "high"
PRIORITY_MEDIUM = "medium"
PRIORITY_LOW = "low"

ALL_PRIORITIES = (
    PRIORITY_CRITICAL,
    PRIORITY_HIGH,
    PRIORITY_MEDIUM,
    PRIORITY_LOW,
)

PRIORITY_RANK = {
    PRIORITY_CRITICAL: 4,
    PRIORITY_HIGH: 3,
    PRIORITY_MEDIUM: 2,
    PRIORITY_LOW: 1,
}


# ---------------------------------------------------------------------------#
# Conflict / finding severity constants
# ---------------------------------------------------------------------------#

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

SEVERITY_RANK = {
    SEVERITY_CRITICAL: 4,
    SEVERITY_HIGH: 3,
    SEVERITY_MEDIUM: 2,
    SEVERITY_LOW: 1,
}


# ---------------------------------------------------------------------------#
# Conflict type constants
# ---------------------------------------------------------------------------#

CONFLICT_CIRCULAR_DEPENDENCY = "circular_dependency"
CONFLICT_MISSING_DEPENDENCY = "missing_dependency"
CONFLICT_PHASE_ORDER = "phase_order_violation"
CONFLICT_TASK_ORDER = "task_order_violation"
CONFLICT_PARALLEL_VIOLATION = "parallel_violation"
CONFLICT_MISSING_PHASE = "missing_phase"
CONFLICT_ORPHAN_TASK = "orphan_task"
CONFLICT_DUPLICATE_TASK = "duplicate_task"

ALL_CONFLICT_TYPES = (
    CONFLICT_CIRCULAR_DEPENDENCY,
    CONFLICT_MISSING_DEPENDENCY,
    CONFLICT_PHASE_ORDER,
    CONFLICT_TASK_ORDER,
    CONFLICT_PARALLEL_VIOLATION,
    CONFLICT_MISSING_PHASE,
    CONFLICT_ORPHAN_TASK,
    CONFLICT_DUPLICATE_TASK,
)


# ---------------------------------------------------------------------------#
# Quality rule constants
# ---------------------------------------------------------------------------#

RULE_NO_CRITICAL_CONFLICTS = "no_critical_conflicts"
RULE_ALL_PHASES_PRESENT = "all_phases_present"
RULE_ALL_TASKS_ORDERED = "all_tasks_ordered"
RULE_NO_CIRCULAR_DEPENDENCIES = "no_circular_dependencies"
RULE_NO_MISSING_DEPENDENCIES = "no_missing_dependencies"
RULE_PLAN_COMPLETE = "plan_complete"
RULE_SUFFICIENT_CONFIDENCE = "sufficient_confidence"

ALL_QUALITY_RULES = (
    RULE_NO_CRITICAL_CONFLICTS,
    RULE_ALL_PHASES_PRESENT,
    RULE_ALL_TASKS_ORDERED,
    RULE_NO_CIRCULAR_DEPENDENCIES,
    RULE_NO_MISSING_DEPENDENCIES,
    RULE_PLAN_COMPLETE,
    RULE_SUFFICIENT_CONFIDENCE,
)


# ---------------------------------------------------------------------------#
# Cache status constants
# ---------------------------------------------------------------------------#

CACHE_HIT = "hit"
CACHE_MISS = "miss"
CACHE_STALE = "stale"
CACHE_DISABLED = "disabled"

ALL_CACHE_STATUSES = (
    CACHE_HIT,
    CACHE_MISS,
    CACHE_STALE,
    CACHE_DISABLED,
)


# ---------------------------------------------------------------------------#
# Confidence level constants
# ---------------------------------------------------------------------------#

CONFIDENCE_HIGH = "high"
CONFIDENCE_MEDIUM = "medium"
CONFIDENCE_LOW = "low"

ALL_CONFIDENCE_LEVELS = (
    CONFIDENCE_HIGH,
    CONFIDENCE_MEDIUM,
    CONFIDENCE_LOW,
)

CONFIDENCE_HIGH_THRESHOLD = 0.85
CONFIDENCE_MEDIUM_THRESHOLD = 0.60


# ---------------------------------------------------------------------------#
# Verdict constants
# ---------------------------------------------------------------------------#

VERDICT_READY = "ready"
VERDICT_READY_WITH_WARNINGS = "ready_with_warnings"
VERDICT_NOT_READY = "not_ready"

ALL_VERDICTS = (
    VERDICT_READY,
    VERDICT_READY_WITH_WARNINGS,
    VERDICT_NOT_READY,
)


# ---------------------------------------------------------------------------#
# Data classes
# ---------------------------------------------------------------------------#

@dataclass
class ExecutionTask:
    """A single atomic task inside the execution plan.

    Attributes:
        task_id: Unique identifier for the task.
        name: Human-readable name.
        description: Detailed description of what the task does.
        phase: The phase this task belongs to.
        priority: Execution priority (critical/high/medium/low).
        depends_on: List of task_ids that must complete before this one.
        execution_mode: sequential or parallel.
        estimated_complexity: Relative complexity score (1-10).
        status: Current status of the task.
        tags: Optional classification tags.
        metadata: Arbitrary extra information.
    """

    task_id: str
    name: str
    description: str = ""
    phase: str = PHASE_FOUNDATION
    priority: str = PRIORITY_MEDIUM
    depends_on: List[str] = field(default_factory=list)
    execution_mode: str = EXECUTION_MODE_SEQUENTIAL
    estimated_complexity: int = 5
    status: str = TASK_STATUS_PENDING
    tags: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "task_id": self.task_id,
            "name": self.name,
            "description": self.description,
            "phase": self.phase,
            "priority": self.priority,
            "depends_on": list(self.depends_on),
            "execution_mode": self.execution_mode,
            "estimated_complexity": self.estimated_complexity,
            "status": self.status,
            "tags": list(self.tags),
            "metadata": dict(self.metadata),
        }


@dataclass
class ExecutionPhase:
    """A logical phase that groups related tasks.

    Attributes:
        phase_id: Unique identifier (matches one of ALL_PHASES).
        name: Human-readable name.
        description: Purpose of the phase.
        order: Numeric order used for sorting.
        tasks: List of ExecutionTask belonging to this phase.
        depends_on_phases: Other phase_ids that must finish first.
        can_run_parallel_with: Phase ids that may run concurrently.
        status: Aggregated status of the phase.
    """

    phase_id: str
    name: str
    description: str = ""
    order: int = 0
    tasks: List[ExecutionTask] = field(default_factory=list)
    depends_on_phases: List[str] = field(default_factory=list)
    can_run_parallel_with: List[str] = field(default_factory=list)
    status: str = TASK_STATUS_PENDING

    def to_dict(self) -> Dict[str, Any]:
        return {
            "phase_id": self.phase_id,
            "name": self.name,
            "description": self.description,
            "order": self.order,
            "tasks": [t.to_dict() for t in self.tasks],
            "depends_on_phases": list(self.depends_on_phases),
            "can_run_parallel_with": list(self.can_run_parallel_with),
            "status": self.status,
        }


@dataclass
class TaskDependency:
    """A directed dependency edge between two tasks.

    Attributes:
        from_task_id: The prerequisite task.
        to_task_id: The dependent task.
        dependency_type: hard / soft / ordering.
        reason: Why this dependency exists.
    """

    from_task_id: str
    to_task_id: str
    dependency_type: str = "hard"
    reason: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "from_task_id": self.from_task_id,
            "to_task_id": self.to_task_id,
            "dependency_type": self.dependency_type,
            "reason": self.reason,
        }


@dataclass
class ParallelGroup:
    """A group of tasks that may execute concurrently.

    Attributes:
        group_id: Unique identifier.
        task_ids: Tasks that can run in parallel.
        phase: The phase these tasks belong to.
        reason: Why they are considered parallel-safe.
    """

    group_id: str
    task_ids: List[str] = field(default_factory=list)
    phase: str = ""
    reason: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "group_id": self.group_id,
            "task_ids": list(self.task_ids),
            "phase": self.phase,
            "reason": self.reason,
        }


@dataclass
class ExecutionConflict:
    """A detected conflict that may invalidate the plan.

    Attributes:
        conflict_id: Unique identifier.
        conflict_type: One of ALL_CONFLICT_TYPES.
        severity: critical / high / medium / low.
        message: Human-readable description.
        affected_tasks: Task ids involved.
        affected_phases: Phase ids involved.
        resolution_hint: Suggested fix.
    """

    conflict_id: str
    conflict_type: str
    severity: str = SEVERITY_HIGH
    message: str = ""
    affected_tasks: List[str] = field(default_factory=list)
    affected_phases: List[str] = field(default_factory=list)
    resolution_hint: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "conflict_id": self.conflict_id,
            "conflict_type": self.conflict_type,
            "severity": self.severity,
            "message": self.message,
            "affected_tasks": list(self.affected_tasks),
            "affected_phases": list(self.affected_phases),
            "resolution_hint": self.resolution_hint,
        }


@dataclass
class ExecutionFinding:
    """A quality or validation finding produced during planning.

    Attributes:
        severity: critical / high / medium / low.
        code: Machine-readable code.
        message: Human-readable message.
        affected: What is affected.
        resolution_hint: How to resolve.
        category: quality / ordering / dependency / conflict.
    """

    severity: str
    code: str
    message: str
    affected: str = ""
    resolution_hint: str = ""
    category: str = "quality"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "severity": self.severity,
            "code": self.code,
            "message": self.message,
            "affected": self.affected,
            "resolution_hint": self.resolution_hint,
            "category": self.category,
        }


@dataclass
class CacheInfo:
    """Cache metadata for the execution plan.

    Attributes:
        status: hit / miss / stale / disabled.
        key: The cache key used.
        created_at: ISO timestamp when the entry was created.
        hits: Number of times this entry was served.
    """

    status: str = CACHE_MISS
    key: str = ""
    created_at: str = ""
    hits: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "status": self.status,
            "key": self.key,
            "created_at": self.created_at,
            "hits": self.hits,
        }


@dataclass
class ExecutionProvenance:
    """Provenance information for the generated plan.

    Attributes:
        engine_name: Name of the producing engine.
        engine_version: Version of the engine.
        sources_used: List of source artefact names that were available.
        sources_missing: List of source artefact names that were absent.
        generated_at: ISO timestamp.
        confidence: Overall confidence score (0.0-1.0).
        confidence_level: high / medium / low.
    """

    engine_name: str = "execution_planning"
    engine_version: str = "1.0.0"
    sources_used: List[str] = field(default_factory=list)
    sources_missing: List[str] = field(default_factory=list)
    generated_at: str = ""
    confidence: float = 0.0
    confidence_level: str = CONFIDENCE_LOW

    def to_dict(self) -> Dict[str, Any]:
        return {
            "engine_name": self.engine_name,
            "engine_version": self.engine_version,
            "sources_used": list(self.sources_used),
            "sources_missing": list(self.sources_missing),
            "generated_at": self.generated_at,
            "confidence": self.confidence,
            "confidence_level": self.confidence_level,
        }


@dataclass
class ExecutionPlan:
    """The complete, authoritative Execution Plan.

    This is the sole output of the Execution Planning Engine.
    Downstream engines must treat it as the single source of truth
    for the order of operations.

    Attributes:
        plan_id: Unique identifier for this plan instance.
        phases: Ordered list of ExecutionPhase objects.
        tasks: Flat list of all ExecutionTask objects.
        dependencies: All TaskDependency edges.
        parallel_groups: Groups of tasks that may run concurrently.
        sequential_task_ids: Explicit ordered list of sequential tasks.
        conflicts: Detected conflicts (should be empty for a valid plan).
        findings: Quality / validation findings.
        execution_order: Flat ordered list of task_ids representing
            the recommended global execution sequence.
        priority_map: Mapping of task_id → priority.
        readiness_status: Overall readiness (ready / ready_with_warnings / not_ready).
        verdict: Final verdict after quality gate.
        cache_info: Cache metadata.
        provenance: Provenance and confidence information.
        metadata: Arbitrary extra information.
        is_empty: True when the plan contains no useful content.
    """

    plan_id: str = ""
    phases: List[ExecutionPhase] = field(default_factory=list)
    tasks: List[ExecutionTask] = field(default_factory=list)
    dependencies: List[TaskDependency] = field(default_factory=list)
    parallel_groups: List[ParallelGroup] = field(default_factory=list)
    sequential_task_ids: List[str] = field(default_factory=list)
    conflicts: List[ExecutionConflict] = field(default_factory=list)
    findings: List[ExecutionFinding] = field(default_factory=list)
    execution_order: List[str] = field(default_factory=list)
    priority_map: Dict[str, str] = field(default_factory=dict)
    readiness_status: str = VERDICT_NOT_READY
    verdict: str = VERDICT_NOT_READY
    cache_info: CacheInfo = field(default_factory=CacheInfo)
    provenance: ExecutionProvenance = field(default_factory=ExecutionProvenance)
    metadata: Dict[str, Any] = field(default_factory=dict)
    is_empty: bool = True

    def to_dict(self) -> Dict[str, Any]:
        return {
            "plan_id": self.plan_id,
            "phases": [p.to_dict() for p in self.phases],
            "tasks": [t.to_dict() for t in self.tasks],
            "dependencies": [d.to_dict() for d in self.dependencies],
            "parallel_groups": [g.to_dict() for g in self.parallel_groups],
            "sequential_task_ids": list(self.sequential_task_ids),
            "conflicts": [c.to_dict() for c in self.conflicts],
            "findings": [f.to_dict() for f in self.findings],
            "execution_order": list(self.execution_order),
            "priority_map": dict(self.priority_map),
            "readiness_status": self.readiness_status,
            "verdict": self.verdict,
            "cache_info": self.cache_info.to_dict(),
            "provenance": self.provenance.to_dict(),
            "metadata": dict(self.metadata),
            "is_empty": self.is_empty,
        }


__all__ = [
    # Source constants
    "SOURCE_NORMALIZED_REQUIREMENTS",
    "SOURCE_ARCHITECTURE_DECISION",
    "SOURCE_TECHNOLOGY_SELECTION",
    "SOURCE_RISK_ANALYSIS",
    "SOURCE_PROJECT_CAPABILITY",
    "SOURCE_KNOWLEDGE_BASE",
    "ALL_SOURCES",
    # Phase constants
    "PHASE_FOUNDATION",
    "PHASE_CORE_SYSTEM",
    "PHASE_FEATURES",
    "PHASE_INTEGRATIONS",
    "PHASE_TESTING",
    "PHASE_OPTIMIZATION",
    "PHASE_DEPLOYMENT_PREPARATION",
    "ALL_PHASES",
    "PHASE_ORDER",
    # Task / mode constants
    "TASK_STATUS_PENDING",
    "TASK_STATUS_READY",
    "TASK_STATUS_BLOCKED",
    "TASK_STATUS_COMPLETED",
    "ALL_TASK_STATUSES",
    "EXECUTION_MODE_SEQUENTIAL",
    "EXECUTION_MODE_PARALLEL",
    "ALL_EXECUTION_MODES",
    # Priority constants
    "PRIORITY_CRITICAL",
    "PRIORITY_HIGH",
    "PRIORITY_MEDIUM",
    "PRIORITY_LOW",
    "ALL_PRIORITIES",
    "PRIORITY_RANK",
    # Severity constants
    "SEVERITY_CRITICAL",
    "SEVERITY_HIGH",
    "SEVERITY_MEDIUM",
    "SEVERITY_LOW",
    "ALL_SEVERITIES",
    "SEVERITY_RANK",
    # Conflict type constants
    "CONFLICT_CIRCULAR_DEPENDENCY",
    "CONFLICT_MISSING_DEPENDENCY",
    "CONFLICT_PHASE_ORDER",
    "CONFLICT_TASK_ORDER",
    "CONFLICT_PARALLEL_VIOLATION",
    "CONFLICT_MISSING_PHASE",
    "CONFLICT_ORPHAN_TASK",
    "CONFLICT_DUPLICATE_TASK",
    "ALL_CONFLICT_TYPES",
    # Quality rule constants
    "RULE_NO_CRITICAL_CONFLICTS",
    "RULE_ALL_PHASES_PRESENT",
    "RULE_ALL_TASKS_ORDERED",
    "RULE_NO_CIRCULAR_DEPENDENCIES",
    "RULE_NO_MISSING_DEPENDENCIES",
    "RULE_PLAN_COMPLETE",
    "RULE_SUFFICIENT_CONFIDENCE",
    "ALL_QUALITY_RULES",
    # Cache constants
    "CACHE_HIT",
    "CACHE_MISS",
    "CACHE_STALE",
    "CACHE_DISABLED",
    "ALL_CACHE_STATUSES",
    # Confidence constants
    "CONFIDENCE_HIGH",
    "CONFIDENCE_MEDIUM",
    "CONFIDENCE_LOW",
    "ALL_CONFIDENCE_LEVELS",
    "CONFIDENCE_HIGH_THRESHOLD",
    "CONFIDENCE_MEDIUM_THRESHOLD",
    # Verdict constants
    "VERDICT_READY",
    "VERDICT_READY_WITH_WARNINGS",
    "VERDICT_NOT_READY",
    "ALL_VERDICTS",
    # Data classes
    "ExecutionTask",
    "ExecutionPhase",
    "TaskDependency",
    "ParallelGroup",
    "ExecutionConflict",
    "ExecutionFinding",
    "CacheInfo",
    "ExecutionProvenance",
    "ExecutionPlan",
]
