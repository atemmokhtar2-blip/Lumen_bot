"""
Generation Session Report data model (Specification 028).

Orchestrates the entire project generation process without writing code itself.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


SOURCE_READINESS = "generation_readiness_report"
SOURCE_STRATEGY = "generation_strategy_blueprint"
SOURCE_EXECUTION_PLAN = "execution_plan"
SOURCE_PROJECT_STRUCTURE = "project_structure_blueprint"
SOURCE_MODULE_ARCHITECTURE = "module_architecture_blueprint"
SOURCE_COMPONENT_ARCHITECTURE = "component_architecture_blueprint"
SOURCE_INTERFACE_CONTRACT = "interface_contract_blueprint"
SOURCE_RESOURCE_DEPENDENCY = "resource_dependency_blueprint"

ALL_SOURCES = (
    SOURCE_READINESS,
    SOURCE_STRATEGY,
    SOURCE_EXECUTION_PLAN,
    SOURCE_PROJECT_STRUCTURE,
    SOURCE_MODULE_ARCHITECTURE,
    SOURCE_COMPONENT_ARCHITECTURE,
    SOURCE_INTERFACE_CONTRACT,
    SOURCE_RESOURCE_DEPENDENCY,
)

# Session statuses
STATUS_PENDING = "pending"
STATUS_RUNNING = "running"
STATUS_PAUSED = "paused"
STATUS_COMPLETED = "completed"
STATUS_FAILED = "failed"
STATUS_CANCELLED = "cancelled"

ALL_STATUSES = (
    STATUS_PENDING, STATUS_RUNNING, STATUS_PAUSED,
    STATUS_COMPLETED, STATUS_FAILED, STATUS_CANCELLED,
)

# Task statuses
TASK_PENDING = "pending"
TASK_ASSIGNED = "assigned"
TASK_RUNNING = "running"
TASK_COMPLETED = "completed"
TASK_FAILED = "failed"
TASK_SKIPPED = "skipped"

# Phases mirror strategy stages
PHASE_FOUNDATION = "foundation"
PHASE_CORE = "core"
PHASE_FEATURES = "features"
PHASE_INTEGRATION = "integration"
PHASE_CONFIGURATION = "configuration"
PHASE_TESTING = "testing"
PHASE_DOCUMENTATION = "documentation"
PHASE_FINALIZE = "finalize"

ALL_PHASES = (
    PHASE_FOUNDATION, PHASE_CORE, PHASE_FEATURES, PHASE_INTEGRATION,
    PHASE_CONFIGURATION, PHASE_TESTING, PHASE_DOCUMENTATION, PHASE_FINALIZE,
)

SEVERITY_CRITICAL = "critical"
SEVERITY_HIGH = "high"
SEVERITY_MEDIUM = "medium"
SEVERITY_LOW = "low"

CACHE_HIT = "hit"
CACHE_MISS = "miss"
CACHE_DISABLED = "disabled"

CONFIDENCE_HIGH = "high"
CONFIDENCE_MEDIUM = "medium"
CONFIDENCE_LOW = "low"
CONFIDENCE_HIGH_THRESHOLD = 0.85
CONFIDENCE_MEDIUM_THRESHOLD = 0.60

VERDICT_READY = "ready"
VERDICT_READY_WITH_WARNINGS = "ready_with_warnings"
VERDICT_NOT_READY = "not_ready"

ALL_VERDICTS = (VERDICT_READY, VERDICT_READY_WITH_WARNINGS, VERDICT_NOT_READY)

RULE_SESSION_CREATED = "session_created"
RULE_TASKS_DISTRIBUTED = "tasks_distributed"
RULE_NO_CRITICAL_ERRORS = "no_critical_errors"
RULE_CHECKPOINTS_DEFINED = "checkpoints_defined"
RULE_READINESS_APPROVED = "readiness_approved"
RULE_SUFFICIENT_CONFIDENCE = "sufficient_confidence"

ALL_QUALITY_RULES = (
    RULE_SESSION_CREATED,
    RULE_TASKS_DISTRIBUTED,
    RULE_NO_CRITICAL_ERRORS,
    RULE_CHECKPOINTS_DEFINED,
    RULE_READINESS_APPROVED,
    RULE_SUFFICIENT_CONFIDENCE,
)


@dataclass
class GenerationTask:
    task_id: str
    name: str
    phase: str = PHASE_FOUNDATION
    assigned_engine: str = ""
    status: str = TASK_PENDING
    depends_on: List[str] = field(default_factory=list)
    item_ref: str = ""          # reference to strategy item_id
    path: str = ""
    started_at: str = ""
    finished_at: str = ""
    error: str = ""
    order: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "task_id": self.task_id,
            "name": self.name,
            "phase": self.phase,
            "assigned_engine": self.assigned_engine,
            "status": self.status,
            "depends_on": list(self.depends_on),
            "item_ref": self.item_ref,
            "path": self.path,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "error": self.error,
            "order": self.order,
        }


@dataclass
class Checkpoint:
    checkpoint_id: str
    after_phase: str
    created_at: str = ""
    description: str = ""
    completed_task_ids: List[str] = field(default_factory=list)
    snapshot_keys: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "checkpoint_id": self.checkpoint_id,
            "after_phase": self.after_phase,
            "created_at": self.created_at,
            "description": self.description,
            "completed_task_ids": list(self.completed_task_ids),
            "snapshot_keys": list(self.snapshot_keys),
        }


@dataclass
class SessionLogEntry:
    entry_id: str
    timestamp: str
    source: str
    event: str
    result: str = ""
    details: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "entry_id": self.entry_id,
            "timestamp": self.timestamp,
            "source": self.source,
            "event": self.event,
            "result": self.result,
            "details": self.details,
        }


@dataclass
class ProgressInfo:
    total_tasks: int = 0
    completed_tasks: int = 0
    failed_tasks: int = 0
    pending_tasks: int = 0
    percent: float = 0.0
    current_phase: str = ""
    estimated_remaining_seconds: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "total_tasks": self.total_tasks,
            "completed_tasks": self.completed_tasks,
            "failed_tasks": self.failed_tasks,
            "pending_tasks": self.pending_tasks,
            "percent": self.percent,
            "current_phase": self.current_phase,
            "estimated_remaining_seconds": self.estimated_remaining_seconds,
        }


@dataclass
class OrchestratorFinding:
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
class OrchestratorProvenance:
    engine_name: str = "generation_orchestrator"
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
class GenerationSessionReport:
    """Complete Generation Session Report."""

    session_id: str = ""
    project_id: str = ""
    status: str = STATUS_PENDING
    current_phase: str = ""
    started_at: str = ""
    finished_at: str = ""
    tasks: List[GenerationTask] = field(default_factory=list)
    checkpoints: List[Checkpoint] = field(default_factory=list)
    logs: List[SessionLogEntry] = field(default_factory=list)
    progress: ProgressInfo = field(default_factory=ProgressInfo)
    findings: List[OrchestratorFinding] = field(default_factory=list)
    readiness_approved: bool = False
    readiness_score: float = 0.0
    readiness_status: str = VERDICT_NOT_READY
    verdict: str = VERDICT_NOT_READY
    cache_info: CacheInfo = field(default_factory=CacheInfo)
    provenance: OrchestratorProvenance = field(default_factory=OrchestratorProvenance)
    metadata: Dict[str, Any] = field(default_factory=dict)
    is_empty: bool = True

    def to_dict(self) -> Dict[str, Any]:
        return {
            "session_id": self.session_id,
            "project_id": self.project_id,
            "status": self.status,
            "current_phase": self.current_phase,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "tasks": [t.to_dict() for t in self.tasks],
            "checkpoints": [c.to_dict() for c in self.checkpoints],
            "logs": [e.to_dict() for e in self.logs],
            "progress": self.progress.to_dict(),
            "findings": [f.to_dict() for f in self.findings],
            "readiness_approved": self.readiness_approved,
            "readiness_score": self.readiness_score,
            "readiness_status": self.readiness_status,
            "verdict": self.verdict,
            "cache_info": self.cache_info.to_dict(),
            "provenance": self.provenance.to_dict(),
            "metadata": dict(self.metadata),
            "is_empty": self.is_empty,
        }


__all__ = [
    "SOURCE_READINESS", "SOURCE_STRATEGY", "SOURCE_EXECUTION_PLAN",
    "SOURCE_PROJECT_STRUCTURE", "SOURCE_MODULE_ARCHITECTURE",
    "SOURCE_COMPONENT_ARCHITECTURE", "SOURCE_INTERFACE_CONTRACT",
    "SOURCE_RESOURCE_DEPENDENCY", "ALL_SOURCES",
    "STATUS_PENDING", "STATUS_RUNNING", "STATUS_PAUSED", "STATUS_COMPLETED",
    "STATUS_FAILED", "STATUS_CANCELLED", "ALL_STATUSES",
    "TASK_PENDING", "TASK_ASSIGNED", "TASK_RUNNING", "TASK_COMPLETED",
    "TASK_FAILED", "TASK_SKIPPED",
    "PHASE_FOUNDATION", "PHASE_CORE", "PHASE_FEATURES", "PHASE_INTEGRATION",
    "PHASE_CONFIGURATION", "PHASE_TESTING", "PHASE_DOCUMENTATION", "PHASE_FINALIZE",
    "ALL_PHASES",
    "SEVERITY_CRITICAL", "SEVERITY_HIGH", "SEVERITY_MEDIUM", "SEVERITY_LOW",
    "CACHE_HIT", "CACHE_MISS", "CACHE_DISABLED",
    "CONFIDENCE_HIGH", "CONFIDENCE_MEDIUM", "CONFIDENCE_LOW",
    "CONFIDENCE_HIGH_THRESHOLD", "CONFIDENCE_MEDIUM_THRESHOLD",
    "VERDICT_READY", "VERDICT_READY_WITH_WARNINGS", "VERDICT_NOT_READY", "ALL_VERDICTS",
    "RULE_SESSION_CREATED", "RULE_TASKS_DISTRIBUTED", "RULE_NO_CRITICAL_ERRORS",
    "RULE_CHECKPOINTS_DEFINED", "RULE_READINESS_APPROVED", "RULE_SUFFICIENT_CONFIDENCE",
    "ALL_QUALITY_RULES",
    "GenerationTask", "Checkpoint", "SessionLogEntry", "ProgressInfo",
    "OrchestratorFinding", "CacheInfo", "OrchestratorProvenance",
    "GenerationSessionReport",
]
