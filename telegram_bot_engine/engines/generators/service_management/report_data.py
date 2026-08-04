"""
Service Management Report (Specification 061 — MAXIMUM CRITICAL).

Central service registry and lifecycle: register, start, stop, restart,
health, recovery, isolation, load and resource allocation.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List


SOURCE_SECURITY = "security_permission_report"
SOURCE_CONFIG = "configuration_management_report"
SOURCE_MONITORING = "system_monitoring_report"
SOURCE_RESOURCE = "resource_management_report"
SOURCE_EXECUTION_CONTEXT = "execution_context_report"
SOURCE_ECOSYSTEM = "engine_ecosystem_report"
SOURCE_USER_REQUEST = "user_request"

ALL_SOURCES = (
    SOURCE_SECURITY,
    SOURCE_CONFIG,
    SOURCE_MONITORING,
    SOURCE_RESOURCE,
    SOURCE_EXECUTION_CONTEXT,
    SOURCE_ECOSYSTEM,
    SOURCE_USER_REQUEST,
)

SEVERITY_CRITICAL = "critical"
SEVERITY_HIGH = "high"
SEVERITY_MEDIUM = "medium"
SEVERITY_LOW = "low"
SEVERITY_INFO = "info"

# Lifecycle states
STATE_REGISTERED = "registered"
STATE_INITIALIZED = "initialized"
STATE_STARTED = "started"
STATE_PAUSED = "paused"
STATE_STOPPED = "stopped"
STATE_FAILED = "failed"
STATE_RECOVERING = "recovering"
STATE_SHUTDOWN = "shutdown"

ALL_STATES = (
    STATE_REGISTERED, STATE_INITIALIZED, STATE_STARTED, STATE_PAUSED,
    STATE_STOPPED, STATE_FAILED, STATE_RECOVERING, STATE_SHUTDOWN,
)

# Lifecycle actions
ACTION_INIT = "initialize"
ACTION_START = "start"
ACTION_PAUSE = "pause"
ACTION_RESUME = "resume"
ACTION_RESTART = "restart"
ACTION_SHUTDOWN = "shutdown"

ALL_ACTIONS = (
    ACTION_INIT, ACTION_START, ACTION_PAUSE, ACTION_RESUME,
    ACTION_RESTART, ACTION_SHUTDOWN,
)

RULE_REGISTERED_ONLY = "no_unregistered_service"
RULE_DEPENDENCY_ORDER = "dependency_order_respected"
RULE_HEALTH_TRACKED = "health_tracked"
RULE_ISOLATION = "service_isolation_enforced"
RULE_SELF_VERIFICATION = "self_verification_passed"
RULE_QUALITY_PASS = "quality_pass"

ALL_QUALITY_RULES = (
    RULE_REGISTERED_ONLY,
    RULE_DEPENDENCY_ORDER,
    RULE_HEALTH_TRACKED,
    RULE_ISOLATION,
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
class ServiceRecord:
    service_id: str
    name: str
    version: str = "1.0.0"
    dependencies: List[str] = field(default_factory=list)
    priority: int = 100
    state: str = STATE_REGISTERED
    health_status: str = "unknown"  # healthy | degraded | unhealthy | unknown

    def to_dict(self) -> Dict[str, Any]:
        return {
            "service_id": self.service_id,
            "name": self.name,
            "version": self.version,
            "dependencies": list(self.dependencies),
            "priority": self.priority,
            "state": self.state,
            "health_status": self.health_status,
        }


@dataclass
class ServiceHealth:
    service_id: str
    availability: float = 1.0
    response_time_ms: float = 0.0
    error_rate: float = 0.0
    restart_count: int = 0
    status: str = "healthy"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "service_id": self.service_id,
            "availability": self.availability,
            "response_time_ms": self.response_time_ms,
            "error_rate": self.error_rate,
            "restart_count": self.restart_count,
            "status": self.status,
        }


@dataclass
class LifecycleEvent:
    event_id: str
    service_id: str
    action: str
    from_state: str
    to_state: str
    success: bool = True
    message: str = ""
    timestamp: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "event_id": self.event_id,
            "service_id": self.service_id,
            "action": self.action,
            "from_state": self.from_state,
            "to_state": self.to_state,
            "success": self.success,
            "message": self.message,
            "timestamp": self.timestamp,
        }


@dataclass
class RecoveryRecord:
    recovery_id: str
    service_id: str
    action: str  # restart | recovery | isolation
    success: bool = True
    message: str = ""
    timestamp: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "recovery_id": self.recovery_id,
            "service_id": self.service_id,
            "action": self.action,
            "success": self.success,
            "message": self.message,
            "timestamp": self.timestamp,
        }


@dataclass
class ResourceAllocation:
    service_id: str
    cpu_percent: float = 5.0
    ram_mb: float = 64.0
    threads: int = 1

    def to_dict(self) -> Dict[str, Any]:
        return {
            "service_id": self.service_id,
            "cpu_percent": self.cpu_percent,
            "ram_mb": self.ram_mb,
            "threads": self.threads,
        }


@dataclass
class LoadSample:
    service_id: str
    load_percent: float = 0.0
    queue_depth: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "service_id": self.service_id,
            "load_percent": self.load_percent,
            "queue_depth": self.queue_depth,
        }


@dataclass
class ServiceFinding:
    severity: str
    code: str
    message: str
    affected: str = ""
    resolution_hint: str = ""
    category: str = "service"

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
class ServiceProvenance:
    engine_name: str = "service_management"
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
class ServiceManagementReport:
    report_id: str = ""
    services: List[ServiceRecord] = field(default_factory=list)
    health: List[ServiceHealth] = field(default_factory=list)
    lifecycle_events: List[LifecycleEvent] = field(default_factory=list)
    recoveries: List[RecoveryRecord] = field(default_factory=list)
    allocations: List[ResourceAllocation] = field(default_factory=list)
    loads: List[LoadSample] = field(default_factory=list)
    findings: List[ServiceFinding] = field(default_factory=list)
    service_count: int = 0
    started_count: int = 0
    failed_count: int = 0
    recovery_count: int = 0
    unregistered_attempts: int = 0
    dependency_violations: int = 0
    self_verification_passed: bool = False
    readiness_status: str = VERDICT_NOT_READY
    verdict: str = VERDICT_NOT_READY
    cache_info: CacheInfo = field(default_factory=CacheInfo)
    provenance: ServiceProvenance = field(default_factory=ServiceProvenance)
    metadata: Dict[str, Any] = field(default_factory=dict)
    is_empty: bool = True

    def to_dict(self) -> Dict[str, Any]:
        return {
            "report_id": self.report_id,
            "services": [s.to_dict() for s in self.services],
            "health": [h.to_dict() for h in self.health],
            "lifecycle_events": [e.to_dict() for e in self.lifecycle_events],
            "recoveries": [r.to_dict() for r in self.recoveries],
            "allocations": [a.to_dict() for a in self.allocations],
            "loads": [l.to_dict() for l in self.loads],
            "findings": [f.to_dict() for f in self.findings],
            "service_count": self.service_count,
            "started_count": self.started_count,
            "failed_count": self.failed_count,
            "recovery_count": self.recovery_count,
            "unregistered_attempts": self.unregistered_attempts,
            "dependency_violations": self.dependency_violations,
            "self_verification_passed": self.self_verification_passed,
            "readiness_status": self.readiness_status,
            "verdict": self.verdict,
            "cache_info": self.cache_info.to_dict(),
            "provenance": self.provenance.to_dict(),
            "metadata": dict(self.metadata),
            "is_empty": self.is_empty,
        }


__all__ = [
    "SOURCE_SECURITY", "SOURCE_CONFIG", "SOURCE_MONITORING", "SOURCE_RESOURCE",
    "SOURCE_EXECUTION_CONTEXT", "SOURCE_ECOSYSTEM", "SOURCE_USER_REQUEST", "ALL_SOURCES",
    "SEVERITY_CRITICAL", "SEVERITY_HIGH", "SEVERITY_MEDIUM", "SEVERITY_LOW", "SEVERITY_INFO",
    "STATE_REGISTERED", "STATE_INITIALIZED", "STATE_STARTED", "STATE_PAUSED",
    "STATE_STOPPED", "STATE_FAILED", "STATE_RECOVERING", "STATE_SHUTDOWN", "ALL_STATES",
    "ACTION_INIT", "ACTION_START", "ACTION_PAUSE", "ACTION_RESUME",
    "ACTION_RESTART", "ACTION_SHUTDOWN", "ALL_ACTIONS",
    "RULE_REGISTERED_ONLY", "RULE_DEPENDENCY_ORDER", "RULE_HEALTH_TRACKED",
    "RULE_ISOLATION", "RULE_SELF_VERIFICATION", "RULE_QUALITY_PASS", "ALL_QUALITY_RULES",
    "CACHE_HIT", "CACHE_MISS", "CACHE_DISABLED",
    "CONFIDENCE_HIGH", "CONFIDENCE_MEDIUM", "CONFIDENCE_LOW",
    "CONFIDENCE_HIGH_THRESHOLD", "CONFIDENCE_MEDIUM_THRESHOLD",
    "VERDICT_READY", "VERDICT_READY_WITH_WARNINGS", "VERDICT_NOT_READY", "ALL_VERDICTS",
    "ServiceRecord", "ServiceHealth", "LifecycleEvent", "RecoveryRecord",
    "ResourceAllocation", "LoadSample", "ServiceFinding", "CacheInfo",
    "ServiceProvenance", "ServiceManagementReport",
]
