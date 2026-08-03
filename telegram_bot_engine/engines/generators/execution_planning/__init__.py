"""
Execution Planning Engine package (Specification 019).

Converts all previous analysis and planning artefacts into a precise,
ordered Execution Plan that the rest of the generation pipeline can
follow step by step.

Public API
----------
* :class:`ExecutionPlanningEngine` — the main engine class.
* :class:`ExecutionPlan` and related data classes.
* All constants defined in :mod:`report_data`.
"""

from .execution_planning_engine import ExecutionPlanningEngine
from .report_data import (
    # Source constants
    SOURCE_NORMALIZED_REQUIREMENTS,
    SOURCE_ARCHITECTURE_DECISION,
    SOURCE_TECHNOLOGY_SELECTION,
    SOURCE_RISK_ANALYSIS,
    SOURCE_PROJECT_CAPABILITY,
    SOURCE_KNOWLEDGE_BASE,
    ALL_SOURCES,
    # Phase constants
    PHASE_FOUNDATION,
    PHASE_CORE_SYSTEM,
    PHASE_FEATURES,
    PHASE_INTEGRATIONS,
    PHASE_TESTING,
    PHASE_OPTIMIZATION,
    PHASE_DEPLOYMENT_PREPARATION,
    ALL_PHASES,
    PHASE_ORDER,
    # Task / mode constants
    TASK_STATUS_PENDING,
    TASK_STATUS_READY,
    TASK_STATUS_BLOCKED,
    TASK_STATUS_COMPLETED,
    ALL_TASK_STATUSES,
    EXECUTION_MODE_SEQUENTIAL,
    EXECUTION_MODE_PARALLEL,
    ALL_EXECUTION_MODES,
    # Priority constants
    PRIORITY_CRITICAL,
    PRIORITY_HIGH,
    PRIORITY_MEDIUM,
    PRIORITY_LOW,
    ALL_PRIORITIES,
    PRIORITY_RANK,
    # Severity constants
    SEVERITY_CRITICAL,
    SEVERITY_HIGH,
    SEVERITY_MEDIUM,
    SEVERITY_LOW,
    ALL_SEVERITIES,
    SEVERITY_RANK,
    # Conflict type constants
    CONFLICT_CIRCULAR_DEPENDENCY,
    CONFLICT_MISSING_DEPENDENCY,
    CONFLICT_PHASE_ORDER,
    CONFLICT_TASK_ORDER,
    CONFLICT_PARALLEL_VIOLATION,
    CONFLICT_MISSING_PHASE,
    CONFLICT_ORPHAN_TASK,
    CONFLICT_DUPLICATE_TASK,
    ALL_CONFLICT_TYPES,
    # Quality rule constants
    RULE_NO_CRITICAL_CONFLICTS,
    RULE_ALL_PHASES_PRESENT,
    RULE_ALL_TASKS_ORDERED,
    RULE_NO_CIRCULAR_DEPENDENCIES,
    RULE_NO_MISSING_DEPENDENCIES,
    RULE_PLAN_COMPLETE,
    RULE_SUFFICIENT_CONFIDENCE,
    ALL_QUALITY_RULES,
    # Cache constants
    CACHE_HIT,
    CACHE_MISS,
    CACHE_STALE,
    CACHE_DISABLED,
    ALL_CACHE_STATUSES,
    # Confidence constants
    CONFIDENCE_HIGH,
    CONFIDENCE_MEDIUM,
    CONFIDENCE_LOW,
    ALL_CONFIDENCE_LEVELS,
    CONFIDENCE_HIGH_THRESHOLD,
    CONFIDENCE_MEDIUM_THRESHOLD,
    # Verdict constants
    VERDICT_READY,
    VERDICT_READY_WITH_WARNINGS,
    VERDICT_NOT_READY,
    ALL_VERDICTS,
    # Data classes
    ExecutionTask,
    ExecutionPhase,
    TaskDependency,
    ParallelGroup,
    ExecutionConflict,
    ExecutionFinding,
    CacheInfo,
    ExecutionProvenance,
    ExecutionPlan,
)

__all__ = [
    "ExecutionPlanningEngine",
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
