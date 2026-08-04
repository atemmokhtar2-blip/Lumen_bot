"""
Task Scheduler Report (Specification 063 — MAXIMUM CRITICAL).

Central task scheduling: registration, FIFO/priority/deadline/round-robin,
dependencies, delayed/periodic execution, retry, cancellation, load awareness.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List


SOURCE_QUEUE = "message_queue_report"
SOURCE_SERVICE = "service_management_report"
SOURCE_ORCHESTRATOR = "engine_orchestrator_report"
SOURCE_RESOURCE = "resource_management_report"
SOURCE_EXECUTION_CONTEXT = "execution_context_report"
SOURCE_USER_REQUEST = "user_request"

ALL_SOURCES = (
    SOURCE_QUEUE,
    SOURCE_SERVICE,
    SOURCE_ORCHESTRATOR,
    SOURCE_RESOURCE,
    SOURCE_EXECUTION_CONTEXT,
    SOURCE_USER_REQUEST,
)

SEVERITY_CRITICAL = "critical"
SEVERITY_HIGH = "high"
SEVERITY_MEDIUM = "medium"
SEVERITY_LOW = "low"
SEVERITY_INFO = "info"

# Task states
STATE_PENDING = "pending"
STATE_SCHEDULED = "scheduled"
STATE_RUNNING = "running"
STATE_COMPLETED = "completed"
STATE_FAILED = "failed"
STATE_CANCELLED = "cancelled"
STATE_DELAYED = "delayed"

ALL_STATES = (
    STATE_PENDING, STATE_SCHEDULED, STATE_RUNNING, STATE_COMPLETED,
    STATE_FAILED, STATE_CANCELLED, STATE_DELAYED,
)

# Policies
POLICY_FIFO = "fifo"
POLICY_PRIORITY = "priority"
POLICY_DEADLINE = "deadline"
POLICY_ROUND_ROBIN = "round_robin"
POLICY_CUSTOM = "custom"

ALL_POLICIES = (
    POLICY_FIFO, POLICY_PRIORITY, POLICY_DEADLINE, POLICY_ROUND_ROBIN, POLICY_CUSTOM,
)

# Periodic intervals
PERIOD_HOURLY = "hourly"
PERIOD_DAILY = "daily"
PERIOD_WEEKLY = "weekly"
PERIOD_MONTHLY = "monthly"
PERIOD_CUSTOM = "custom"

ALL_PERIODS = (
    PERIOD_HOURLY, PERIOD_DAILY, PERIOD_WEEKLY, PERIOD_MONTHLY, PERIOD_CUSTOM,
)

RULE_NO_EARLY_START = "no_start_before_schedule"
RULE_DEPENDENCIES = "dependencies_respected"
RULE_LOAD_AWARE = "load_awareness_applied"
RULE_SELF_VERIFICATION = "self_verification_passed"
RULE_QUALITY_PASS = "quality_pass"

ALL_QUALITY_RULES = (
    RULE_NO_EARLY_START,
    RULE_DEPENDENCIES,
    RULE_LOAD_AWARE,
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
class ScheduledTask:
    task_id: str
    name: str = ""
    priority: int = 100
    dependencies: List[str] = field(default_factory=list)
    created_at: str = ""
    deadline: str = ""
    scheduled_at: str = ""
    state: str = STATE_PENDING
    policy: str = POLICY_PRIORITY
    period: str = ""
    delay_until: str = ""
    retry_count: int = 0
    max_retries: int = 3
    window_start: str = ""
    window_end: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "task_id": self.task_id,
            "name": self.name,
            "priority": self.priority,
            "dependencies": list(self.dependencies),
            "created_at": self.created_at,
            "deadline": self.deadline,
            "scheduled_at": self.scheduled_at,
            "state": self.state,
            "policy": self.policy,
            "period": self.period,
            "delay_until": self.delay_until,
            "retry_count": self.retry_count,
            "max_retries": self.max_retries,
            "window_start": self.window_start,
            "window_end": self.window_end,
        }


@dataclass
class ScheduleEvent:
    event_id: str
    task_id: str
    action: str  # register | schedule | start | complete | fail | retry | cancel | delay
    from_state: str = ""
    to_state: str = ""
    success: bool = True
    message: str = ""
    timestamp: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "event_id": self.event_id,
            "task_id": self.task_id,
            "action": self.action,
            "from_state": self.from_state,
            "to_state": self.to_state,
            "success": self.success,
            "message": self.message,
            "timestamp": self.timestamp,
        }


@dataclass
class RetrySchedule:
    task_id: str
    attempt: int
    scheduled_at: str
    reason: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "task_id": self.task_id,
            "attempt": self.attempt,
            "scheduled_at": self.scheduled_at,
            "reason": self.reason,
        }


@dataclass
class SchedulerStats:
    pending: int = 0
    running: int = 0
    completed: int = 0
    failed: int = 0
    cancelled: int = 0
    delayed: int = 0
    rescheduled: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "pending": self.pending,
            "running": self.running,
            "completed": self.completed,
            "failed": self.failed,
            "cancelled": self.cancelled,
            "delayed": self.delayed,
            "rescheduled": self.rescheduled,
        }


@dataclass
class SchedulerFinding:
    severity: str
    code: str
    message: str
    affected: str = ""
    resolution_hint: str = ""
    category: str = "scheduler"

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
class SchedulerProvenance:
    engine_name: str = "task_scheduler"
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
class TaskSchedulerReport:
    report_id: str = ""
    tasks: List[ScheduledTask] = field(default_factory=list)
    events: List[ScheduleEvent] = field(default_factory=list)
    retries: List[RetrySchedule] = field(default_factory=list)
    stats: SchedulerStats = field(default_factory=SchedulerStats)
    findings: List[SchedulerFinding] = field(default_factory=list)
    task_count: int = 0
    completed_count: int = 0
    failed_count: int = 0
    cancelled_count: int = 0
    dependency_violations: int = 0
    early_start_violations: int = 0
    load_throttled: int = 0
    policy: str = POLICY_PRIORITY
    self_verification_passed: bool = False
    readiness_status: str = VERDICT_NOT_READY
    verdict: str = VERDICT_NOT_READY
    cache_info: CacheInfo = field(default_factory=CacheInfo)
    provenance: SchedulerProvenance = field(default_factory=SchedulerProvenance)
    metadata: Dict[str, Any] = field(default_factory=dict)
    is_empty: bool = True

    def to_dict(self) -> Dict[str, Any]:
        return {
            "report_id": self.report_id,
            "tasks": [t.to_dict() for t in self.tasks],
            "events": [e.to_dict() for e in self.events],
            "retries": [r.to_dict() for r in self.retries],
            "stats": self.stats.to_dict(),
            "findings": [f.to_dict() for f in self.findings],
            "task_count": self.task_count,
            "completed_count": self.completed_count,
            "failed_count": self.failed_count,
            "cancelled_count": self.cancelled_count,
            "dependency_violations": self.dependency_violations,
            "early_start_violations": self.early_start_violations,
            "load_throttled": self.load_throttled,
            "policy": self.policy,
            "self_verification_passed": self.self_verification_passed,
            "readiness_status": self.readiness_status,
            "verdict": self.verdict,
            "cache_info": self.cache_info.to_dict(),
            "provenance": self.provenance.to_dict(),
            "metadata": dict(self.metadata),
            "is_empty": self.is_empty,
        }


__all__ = [
    "SOURCE_QUEUE", "SOURCE_SERVICE", "SOURCE_ORCHESTRATOR", "SOURCE_RESOURCE",
    "SOURCE_EXECUTION_CONTEXT", "SOURCE_USER_REQUEST", "ALL_SOURCES",
    "SEVERITY_CRITICAL", "SEVERITY_HIGH", "SEVERITY_MEDIUM", "SEVERITY_LOW", "SEVERITY_INFO",
    "STATE_PENDING", "STATE_SCHEDULED", "STATE_RUNNING", "STATE_COMPLETED",
    "STATE_FAILED", "STATE_CANCELLED", "STATE_DELAYED", "ALL_STATES",
    "POLICY_FIFO", "POLICY_PRIORITY", "POLICY_DEADLINE", "POLICY_ROUND_ROBIN",
    "POLICY_CUSTOM", "ALL_POLICIES",
    "PERIOD_HOURLY", "PERIOD_DAILY", "PERIOD_WEEKLY", "PERIOD_MONTHLY",
    "PERIOD_CUSTOM", "ALL_PERIODS",
    "RULE_NO_EARLY_START", "RULE_DEPENDENCIES", "RULE_LOAD_AWARE",
    "RULE_SELF_VERIFICATION", "RULE_QUALITY_PASS", "ALL_QUALITY_RULES",
    "CACHE_HIT", "CACHE_MISS", "CACHE_DISABLED",
    "CONFIDENCE_HIGH", "CONFIDENCE_MEDIUM", "CONFIDENCE_LOW",
    "CONFIDENCE_HIGH_THRESHOLD", "CONFIDENCE_MEDIUM_THRESHOLD",
    "VERDICT_READY", "VERDICT_READY_WITH_WARNINGS", "VERDICT_NOT_READY", "ALL_VERDICTS",
    "ScheduledTask", "ScheduleEvent", "RetrySchedule", "SchedulerStats",
    "SchedulerFinding", "CacheInfo", "SchedulerProvenance", "TaskSchedulerReport",
]
