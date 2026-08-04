"""
Workflow Execution Report (Specification 064 — MAXIMUM CRITICAL).

Execute workflows from plans: stages, sequential/parallel/conditional,
branches, checkpoints, resume, rollback and monitoring.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List


SOURCE_SCHEDULER = "task_scheduler_report"
SOURCE_QUEUE = "message_queue_report"
SOURCE_ORCHESTRATOR = "engine_orchestrator_report"
SOURCE_EXECUTION_CONTEXT = "execution_context_report"
SOURCE_SERVICE = "service_management_report"
SOURCE_USER_REQUEST = "user_request"

ALL_SOURCES = (
    SOURCE_SCHEDULER,
    SOURCE_QUEUE,
    SOURCE_ORCHESTRATOR,
    SOURCE_EXECUTION_CONTEXT,
    SOURCE_SERVICE,
    SOURCE_USER_REQUEST,
)

SEVERITY_CRITICAL = "critical"
SEVERITY_HIGH = "high"
SEVERITY_MEDIUM = "medium"
SEVERITY_LOW = "low"
SEVERITY_INFO = "info"

# Stage states
STAGE_PENDING = "pending"
STAGE_RUNNING = "running"
STAGE_COMPLETED = "completed"
STAGE_FAILED = "failed"
STAGE_SKIPPED = "skipped"
STAGE_ROLLED_BACK = "rolled_back"

ALL_STAGE_STATES = (
    STAGE_PENDING, STAGE_RUNNING, STAGE_COMPLETED,
    STAGE_FAILED, STAGE_SKIPPED, STAGE_ROLLED_BACK,
)

# Execution modes
MODE_SEQUENTIAL = "sequential"
MODE_PARALLEL = "parallel"
MODE_CONDITIONAL = "conditional"

ALL_MODES = (MODE_SEQUENTIAL, MODE_PARALLEL, MODE_CONDITIONAL)

# Branch types
BRANCH_IF = "if"
BRANCH_ELSE = "else"
BRANCH_SWITCH = "switch"
BRANCH_DEFAULT = "default"

ALL_BRANCHES = (BRANCH_IF, BRANCH_ELSE, BRANCH_SWITCH, BRANCH_DEFAULT)

RULE_SEQUENTIAL_GATE = "no_advance_before_success"
RULE_CHECKPOINTS = "checkpoints_created"
RULE_VALIDATED = "stages_validated"
RULE_SELF_VERIFICATION = "self_verification_passed"
RULE_QUALITY_PASS = "quality_pass"

ALL_QUALITY_RULES = (
    RULE_SEQUENTIAL_GATE,
    RULE_CHECKPOINTS,
    RULE_VALIDATED,
    RULE_SELF_VERIFICATION,
    RULE_QUALITY_PASS,
)

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


@dataclass
class WorkflowStage:
    stage_id: str
    name: str = ""
    order: int = 0
    mode: str = MODE_SEQUENTIAL
    state: str = STAGE_PENDING
    condition: str = ""
    branch: str = ""
    depends_on: List[str] = field(default_factory=list)
    engine_id: str = ""
    validated: bool = False
    duration_ms: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "stage_id": self.stage_id,
            "name": self.name,
            "order": self.order,
            "mode": self.mode,
            "state": self.state,
            "condition": self.condition,
            "branch": self.branch,
            "depends_on": list(self.depends_on),
            "engine_id": self.engine_id,
            "validated": self.validated,
            "duration_ms": self.duration_ms,
        }


@dataclass
class Checkpoint:
    checkpoint_id: str
    stage_id: str
    timestamp: str
    snapshot: Dict[str, Any] = field(default_factory=dict)
    valid: bool = True

    def to_dict(self) -> Dict[str, Any]:
        return {
            "checkpoint_id": self.checkpoint_id,
            "stage_id": self.stage_id,
            "timestamp": self.timestamp,
            "snapshot": dict(self.snapshot),
            "valid": self.valid,
        }


@dataclass
class WorkflowEvent:
    event_id: str
    stage_id: str
    action: str  # build | validate | start | complete | fail | skip | checkpoint | resume | rollback
    from_state: str = ""
    to_state: str = ""
    success: bool = True
    message: str = ""
    timestamp: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "event_id": self.event_id,
            "stage_id": self.stage_id,
            "action": self.action,
            "from_state": self.from_state,
            "to_state": self.to_state,
            "success": self.success,
            "message": self.message,
            "timestamp": self.timestamp,
        }


@dataclass
class RollbackRecord:
    rollback_id: str
    from_stage: str
    to_checkpoint: str
    success: bool = True
    message: str = ""
    timestamp: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "rollback_id": self.rollback_id,
            "from_stage": self.from_stage,
            "to_checkpoint": self.to_checkpoint,
            "success": self.success,
            "message": self.message,
            "timestamp": self.timestamp,
        }


@dataclass
class WorkflowStats:
    total_stages: int = 0
    running: int = 0
    completed: int = 0
    failed: int = 0
    skipped: int = 0
    remaining: int = 0
    checkpoints: int = 0
    rollbacks: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "total_stages": self.total_stages,
            "running": self.running,
            "completed": self.completed,
            "failed": self.failed,
            "skipped": self.skipped,
            "remaining": self.remaining,
            "checkpoints": self.checkpoints,
            "rollbacks": self.rollbacks,
        }


@dataclass
class WorkflowFinding:
    severity: str
    code: str
    message: str
    affected: str = ""
    resolution_hint: str = ""
    category: str = "workflow"

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
class WorkflowProvenance:
    engine_name: str = "workflow_execution"
    engine_version: str = "1.0.0"
    sources_used: List[str] = field(default_factory=list)
    sources_missing: List[str] = field(default_factory=list)
    generated_at: str = ""
    confidence: float = 0.0
    confidence_level: str = CONFIDENCE_LOW
    self_verification_passed: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "engine_name": self.engine_name,
            "engine_version": self.engine_version,
            "sources_used": list(self.sources_used),
            "sources_missing": list(self.sources_missing),
            "generated_at": self.generated_at,
            "confidence": self.confidence,
            "confidence_level": self.confidence_level,
            "self_verification_passed": self.self_verification_passed,
        }


@dataclass
class WorkflowExecutionReport:
    report_id: str = ""
    workflow_id: str = ""
    stages: List[WorkflowStage] = field(default_factory=list)
    checkpoints: List[Checkpoint] = field(default_factory=list)
    events: List[WorkflowEvent] = field(default_factory=list)
    rollbacks: List[RollbackRecord] = field(default_factory=list)
    stats: WorkflowStats = field(default_factory=WorkflowStats)
    findings: List[WorkflowFinding] = field(default_factory=list)
    stage_count: int = 0
    completed_count: int = 0
    failed_count: int = 0
    sequential_gate_violations: int = 0
    resumed: bool = False
    rolled_back: bool = False
    self_verification_passed: bool = False
    readiness_status: str = VERDICT_NOT_READY
    verdict: str = VERDICT_NOT_READY
    cache_info: CacheInfo = field(default_factory=CacheInfo)
    provenance: WorkflowProvenance = field(default_factory=WorkflowProvenance)
    metadata: Dict[str, Any] = field(default_factory=dict)
    is_empty: bool = True

    def to_dict(self) -> Dict[str, Any]:
        return {
            "report_id": self.report_id,
            "workflow_id": self.workflow_id,
            "stages": [s.to_dict() for s in self.stages],
            "checkpoints": [c.to_dict() for c in self.checkpoints],
            "events": [e.to_dict() for e in self.events],
            "rollbacks": [r.to_dict() for r in self.rollbacks],
            "stats": self.stats.to_dict(),
            "findings": [f.to_dict() for f in self.findings],
            "stage_count": self.stage_count,
            "completed_count": self.completed_count,
            "failed_count": self.failed_count,
            "sequential_gate_violations": self.sequential_gate_violations,
            "resumed": self.resumed,
            "rolled_back": self.rolled_back,
            "self_verification_passed": self.self_verification_passed,
            "readiness_status": self.readiness_status,
            "verdict": self.verdict,
            "cache_info": self.cache_info.to_dict(),
            "provenance": self.provenance.to_dict(),
            "metadata": dict(self.metadata),
            "is_empty": self.is_empty,
        }


__all__ = [
    "SOURCE_SCHEDULER", "SOURCE_QUEUE", "SOURCE_ORCHESTRATOR",
    "SOURCE_EXECUTION_CONTEXT", "SOURCE_SERVICE", "SOURCE_USER_REQUEST", "ALL_SOURCES",
    "SEVERITY_CRITICAL", "SEVERITY_HIGH", "SEVERITY_MEDIUM", "SEVERITY_LOW", "SEVERITY_INFO",
    "STAGE_PENDING", "STAGE_RUNNING", "STAGE_COMPLETED", "STAGE_FAILED",
    "STAGE_SKIPPED", "STAGE_ROLLED_BACK", "ALL_STAGE_STATES",
    "MODE_SEQUENTIAL", "MODE_PARALLEL", "MODE_CONDITIONAL", "ALL_MODES",
    "BRANCH_IF", "BRANCH_ELSE", "BRANCH_SWITCH", "BRANCH_DEFAULT", "ALL_BRANCHES",
    "RULE_SEQUENTIAL_GATE", "RULE_CHECKPOINTS", "RULE_VALIDATED",
    "RULE_SELF_VERIFICATION", "RULE_QUALITY_PASS", "ALL_QUALITY_RULES",
    "CACHE_HIT", "CACHE_MISS", "CACHE_DISABLED",
    "CONFIDENCE_HIGH", "CONFIDENCE_MEDIUM", "CONFIDENCE_LOW",
    "CONFIDENCE_HIGH_THRESHOLD", "CONFIDENCE_MEDIUM_THRESHOLD",
    "VERDICT_READY", "VERDICT_READY_WITH_WARNINGS", "VERDICT_NOT_READY", "ALL_VERDICTS",
    "WorkflowStage", "Checkpoint", "WorkflowEvent", "RollbackRecord",
    "WorkflowStats", "WorkflowFinding", "CacheInfo", "WorkflowProvenance",
    "WorkflowExecutionReport",
]
