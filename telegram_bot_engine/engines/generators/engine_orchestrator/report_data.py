"""
Engine Orchestrator Report (Specification 053 — MAXIMUM CRITICAL).

Central orchestrator: no engine starts on its own. All execution flows through
this engine — planning, scheduling, dependency resolution, parallel runs,
failure handling, retry, deadlock detection and replanning.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List


SOURCE_ECOSYSTEM = "engine_ecosystem_report"
SOURCE_ENVIRONMENT = "environment_config_report"
SOURCE_DEPENDENCY = "dependency_management_report"
SOURCE_PROJECT_CONTEXT = "project_context_report"
SOURCE_USER_REQUEST = "user_request"

ALL_SOURCES = (
    SOURCE_ECOSYSTEM,
    SOURCE_ENVIRONMENT,
    SOURCE_DEPENDENCY,
    SOURCE_PROJECT_CONTEXT,
    SOURCE_USER_REQUEST,
)

SEVERITY_CRITICAL = "critical"
SEVERITY_HIGH = "high"
SEVERITY_MEDIUM = "medium"
SEVERITY_LOW = "low"
SEVERITY_INFO = "info"

# Task modes
MODE_SEQUENTIAL = "sequential"
MODE_PARALLEL = "parallel"
MODE_CONDITIONAL = "conditional"

# Task status
TASK_PENDING = "pending"
TASK_WAITING = "waiting"
TASK_RUNNING = "running"
TASK_SUCCESS = "success"
TASK_FAILED = "failed"
TASK_SKIPPED = "skipped"
TASK_RETRYING = "retrying"
TASK_CANCELLED = "cancelled"

RULE_NO_DIRECT_CALLS = "no_direct_engine_calls"
RULE_DEPENDENCIES_RESPECTED = "dependencies_respected"
RULE_NO_DEADLOCK = "no_deadlock"
RULE_FAILURE_ISOLATED = "failure_isolated"
RULE_SELF_VERIFICATION = "self_verification_passed"
RULE_QUALITY_PASS = "quality_pass"

ALL_QUALITY_RULES = (
    RULE_NO_DIRECT_CALLS,
    RULE_DEPENDENCIES_RESPECTED,
    RULE_NO_DEADLOCK,
    RULE_FAILURE_ISOLATED,
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
class PlannedTask:
    task_id: str
    engine_id: str
    priority: int = 100
    mode: str = MODE_SEQUENTIAL
    depends_on: List[str] = field(default_factory=list)
    max_retries: int = 2
    status: str = TASK_PENDING
    wave: int = 0  # parallel wave index

    def to_dict(self) -> Dict[str, Any]:
        return {
            "task_id": self.task_id,
            "engine_id": self.engine_id,
            "priority": self.priority,
            "mode": self.mode,
            "depends_on": list(self.depends_on),
            "max_retries": self.max_retries,
            "status": self.status,
            "wave": self.wave,
        }


@dataclass
class ExecutionRecord:
    record_id: str
    engine_id: str
    task_id: str = ""
    status: str = TASK_SUCCESS
    started_at: str = ""
    finished_at: str = ""
    duration_ms: float = 0.0
    waiting_ms: float = 0.0
    attempt: int = 1
    error: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "record_id": self.record_id,
            "engine_id": self.engine_id,
            "task_id": self.task_id,
            "status": self.status,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "duration_ms": self.duration_ms,
            "waiting_ms": self.waiting_ms,
            "attempt": self.attempt,
            "error": self.error,
        }


@dataclass
class ResourceAllocation:
    engine_id: str
    cpu_share: float = 0.1
    ram_mb: float = 64.0
    threads: int = 1

    def to_dict(self) -> Dict[str, Any]:
        return {
            "engine_id": self.engine_id,
            "cpu_share": self.cpu_share,
            "ram_mb": self.ram_mb,
            "threads": self.threads,
        }


@dataclass
class DeadlockInfo:
    deadlock_id: str
    engines: List[str] = field(default_factory=list)
    message: str = ""
    resolved: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "deadlock_id": self.deadlock_id,
            "engines": list(self.engines),
            "message": self.message,
            "resolved": self.resolved,
        }


@dataclass
class PerformanceMetrics:
    total_tasks: int = 0
    success_count: int = 0
    failure_count: int = 0
    retry_count: int = 0
    total_duration_ms: float = 0.0
    avg_duration_ms: float = 0.0
    success_rate: float = 0.0
    parallel_waves: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "total_tasks": self.total_tasks,
            "success_count": self.success_count,
            "failure_count": self.failure_count,
            "retry_count": self.retry_count,
            "total_duration_ms": self.total_duration_ms,
            "avg_duration_ms": self.avg_duration_ms,
            "success_rate": self.success_rate,
            "parallel_waves": self.parallel_waves,
        }


@dataclass
class OrchestratorFinding:
    severity: str
    code: str
    message: str
    affected: str = ""
    resolution_hint: str = ""
    category: str = "orchestrator"

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
    engine_name: str = "engine_orchestrator"
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
class EngineOrchestratorReport:
    report_id: str = ""
    plan: List[PlannedTask] = field(default_factory=list)
    history: List[ExecutionRecord] = field(default_factory=list)
    resources: List[ResourceAllocation] = field(default_factory=list)
    deadlocks: List[DeadlockInfo] = field(default_factory=list)
    metrics: PerformanceMetrics = field(default_factory=PerformanceMetrics)
    findings: List[OrchestratorFinding] = field(default_factory=list)
    task_count: int = 0
    failure_count: int = 0
    deadlock_count: int = 0
    replanned: bool = False
    self_verification_passed: bool = False
    readiness_status: str = VERDICT_NOT_READY
    verdict: str = VERDICT_NOT_READY
    cache_info: CacheInfo = field(default_factory=CacheInfo)
    provenance: OrchestratorProvenance = field(default_factory=OrchestratorProvenance)
    metadata: Dict[str, Any] = field(default_factory=dict)
    is_empty: bool = True

    def to_dict(self) -> Dict[str, Any]:
        return {
            "report_id": self.report_id,
            "plan": [p.to_dict() for p in self.plan],
            "history": [h.to_dict() for h in self.history],
            "resources": [r.to_dict() for r in self.resources],
            "deadlocks": [d.to_dict() for d in self.deadlocks],
            "metrics": self.metrics.to_dict(),
            "findings": [f.to_dict() for f in self.findings],
            "task_count": self.task_count,
            "failure_count": self.failure_count,
            "deadlock_count": self.deadlock_count,
            "replanned": self.replanned,
            "self_verification_passed": self.self_verification_passed,
            "readiness_status": self.readiness_status,
            "verdict": self.verdict,
            "cache_info": self.cache_info.to_dict(),
            "provenance": self.provenance.to_dict(),
            "metadata": dict(self.metadata),
            "is_empty": self.is_empty,
        }


__all__ = [
    "SOURCE_ECOSYSTEM", "SOURCE_ENVIRONMENT", "SOURCE_DEPENDENCY",
    "SOURCE_PROJECT_CONTEXT", "SOURCE_USER_REQUEST", "ALL_SOURCES",
    "SEVERITY_CRITICAL", "SEVERITY_HIGH", "SEVERITY_MEDIUM", "SEVERITY_LOW", "SEVERITY_INFO",
    "MODE_SEQUENTIAL", "MODE_PARALLEL", "MODE_CONDITIONAL",
    "TASK_PENDING", "TASK_WAITING", "TASK_RUNNING", "TASK_SUCCESS", "TASK_FAILED",
    "TASK_SKIPPED", "TASK_RETRYING", "TASK_CANCELLED",
    "RULE_NO_DIRECT_CALLS", "RULE_DEPENDENCIES_RESPECTED", "RULE_NO_DEADLOCK",
    "RULE_FAILURE_ISOLATED", "RULE_SELF_VERIFICATION", "RULE_QUALITY_PASS",
    "ALL_QUALITY_RULES",
    "CACHE_HIT", "CACHE_MISS", "CACHE_DISABLED",
    "CONFIDENCE_HIGH", "CONFIDENCE_MEDIUM", "CONFIDENCE_LOW",
    "CONFIDENCE_HIGH_THRESHOLD", "CONFIDENCE_MEDIUM_THRESHOLD",
    "VERDICT_READY", "VERDICT_READY_WITH_WARNINGS", "VERDICT_NOT_READY", "ALL_VERDICTS",
    "PlannedTask", "ExecutionRecord", "ResourceAllocation", "DeadlockInfo",
    "PerformanceMetrics", "OrchestratorFinding", "CacheInfo", "OrchestratorProvenance",
    "EngineOrchestratorReport",
]
