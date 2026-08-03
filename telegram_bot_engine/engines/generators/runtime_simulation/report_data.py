"""
Runtime Simulation Report (Specification 040 — ULTRA CRITICAL).

Intelligent Runtime Simulation & Verification Engine artefacts.
Simulates project execution before real delivery; runtime failures block.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List


SOURCE_STATIC_ANALYSIS = "static_analysis_report"
SOURCE_ARCHITECTURE_COMPLIANCE = "architecture_compliance_report"
SOURCE_PERFORMANCE = "performance_optimization_report"
SOURCE_SECURITY = "security_review_report"
SOURCE_CODE_REFACTORING = "code_refactoring_report"
SOURCE_PROJECT_CONTEXT = "project_context_report"

ALL_SOURCES = (
    SOURCE_STATIC_ANALYSIS,
    SOURCE_ARCHITECTURE_COMPLIANCE,
    SOURCE_PERFORMANCE,
    SOURCE_SECURITY,
    SOURCE_CODE_REFACTORING,
    SOURCE_PROJECT_CONTEXT,
)

SEVERITY_CRITICAL = "critical"
SEVERITY_HIGH = "high"
SEVERITY_MEDIUM = "medium"
SEVERITY_LOW = "low"
SEVERITY_INFO = "info"

# Event / failure types
EVT_STARTUP = "startup"
EVT_INIT = "initialization"
EVT_CONFIG = "config_load"
EVT_DI = "dependency_injection"
EVT_ROUTER = "router_init"
EVT_EVENT_REG = "event_registration"
EVT_COMMAND = "command"
EVT_CALLBACK = "callback"
EVT_MESSAGE = "message"
EVT_FILE = "file"
EVT_MEDIA = "media"
EVT_ERROR = "error"
EVT_TIMEOUT = "timeout"
EVT_BACKGROUND = "background_task"
EVT_TG_UPDATE = "telegram_update"
EVT_TG_INLINE = "inline_query"
EVT_NETWORK_FAIL = "network_failure"
EVT_API_FAIL = "api_failure"
EVT_PERM_FAIL = "permission_failure"
EVT_MEMORY = "memory_pressure"
EVT_CPU = "high_cpu"
EVT_STORAGE = "storage_failure"
EVT_CRASH = "crash"
EVT_EXCEPTION = "exception"
EVT_DEADLOCK = "deadlock"
EVT_INFINITE = "infinite_loop"
EVT_LEAK = "memory_leak"
EVT_RECOVER = "recovery"
EVT_RETRY = "retry"
EVT_SHUTDOWN = "graceful_shutdown"
EVT_RESTART = "graceful_restart"

ALL_EVENT_TYPES = (
    EVT_STARTUP, EVT_INIT, EVT_CONFIG, EVT_DI, EVT_ROUTER, EVT_EVENT_REG,
    EVT_COMMAND, EVT_CALLBACK, EVT_MESSAGE, EVT_FILE, EVT_MEDIA,
    EVT_ERROR, EVT_TIMEOUT, EVT_BACKGROUND, EVT_TG_UPDATE, EVT_TG_INLINE,
    EVT_NETWORK_FAIL, EVT_API_FAIL, EVT_PERM_FAIL, EVT_MEMORY, EVT_CPU,
    EVT_STORAGE, EVT_CRASH, EVT_EXCEPTION, EVT_DEADLOCK, EVT_INFINITE,
    EVT_LEAK, EVT_RECOVER, EVT_RETRY, EVT_SHUTDOWN, EVT_RESTART,
)

RULE_NO_RUNTIME_ERROR = "no_runtime_error"
RULE_NO_CRASH = "no_crash"
RULE_NO_FAILURE = "no_critical_failure"
RULE_NO_MEMORY_LEAK = "no_memory_leak"
RULE_STARTUP_OK = "startup_success"
RULE_SELF_VERIFICATION = "self_verification_passed"
RULE_QUALITY_PASS = "quality_pass"
RULE_SUFFICIENT_CONFIDENCE = "sufficient_confidence"

ALL_QUALITY_RULES = (
    RULE_NO_RUNTIME_ERROR,
    RULE_NO_CRASH,
    RULE_NO_FAILURE,
    RULE_NO_MEMORY_LEAK,
    RULE_STARTUP_OK,
    RULE_SELF_VERIFICATION,
    RULE_QUALITY_PASS,
    RULE_SUFFICIENT_CONFIDENCE,
)

MIN_RUNTIME_SCORE = 70.0
MIN_STABILITY = 70.0

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

STATUS_PASSED = "passed"
STATUS_FAILED = "failed"
STATUS_SKIPPED = "skipped"
STATUS_WARNING = "warning"


@dataclass
class SimulationEvent:
    event_id: str
    event_type: str
    status: str = STATUS_PASSED
    severity: str = SEVERITY_INFO
    message: str = ""
    duration_ms: float = 0.0
    details: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "event_id": self.event_id,
            "event_type": self.event_type,
            "status": self.status,
            "severity": self.severity,
            "message": self.message,
            "duration_ms": self.duration_ms,
            "details": dict(self.details),
        }


@dataclass
class StressResult:
    users: int
    concurrent_requests: int = 0
    success_rate: float = 100.0
    avg_latency_ms: float = 0.0
    p99_latency_ms: float = 0.0
    errors: int = 0
    status: str = STATUS_PASSED
    notes: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "users": self.users,
            "concurrent_requests": self.concurrent_requests,
            "success_rate": self.success_rate,
            "avg_latency_ms": self.avg_latency_ms,
            "p99_latency_ms": self.p99_latency_ms,
            "errors": self.errors,
            "status": self.status,
            "notes": self.notes,
        }


@dataclass
class FailureScenario:
    scenario_id: str
    scenario_type: str
    recovered: bool = False
    status: str = STATUS_PASSED
    message: str = ""
    recovery_ms: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "scenario_id": self.scenario_id,
            "scenario_type": self.scenario_type,
            "recovered": self.recovered,
            "status": self.status,
            "message": self.message,
            "recovery_ms": self.recovery_ms,
        }


@dataclass
class ResourceSample:
    cpu_pct: float = 0.0
    ram_mb: float = 0.0
    disk_mb: float = 0.0
    network_kb: float = 0.0
    exec_time_ms: float = 0.0
    response_time_ms: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "cpu_pct": self.cpu_pct,
            "ram_mb": self.ram_mb,
            "disk_mb": self.disk_mb,
            "network_kb": self.network_kb,
            "exec_time_ms": self.exec_time_ms,
            "response_time_ms": self.response_time_ms,
        }


@dataclass
class RuntimeScore:
    stability: float = 0.0
    reliability: float = 0.0
    availability: float = 0.0
    fault_tolerance: float = 0.0
    recovery: float = 0.0
    runtime_performance: float = 0.0
    overall: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "stability": self.stability,
            "reliability": self.reliability,
            "availability": self.availability,
            "fault_tolerance": self.fault_tolerance,
            "recovery": self.recovery,
            "runtime_performance": self.runtime_performance,
            "overall": self.overall,
        }


@dataclass
class RuntimeFinding:
    severity: str
    code: str
    message: str
    affected: str = ""
    resolution_hint: str = ""
    category: str = "runtime"

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
class RuntimeProvenance:
    engine_name: str = "runtime_simulation"
    engine_version: str = "1.0.0"
    sources_used: List[str] = field(default_factory=list)
    sources_missing: List[str] = field(default_factory=list)
    generated_at: str = ""
    confidence: float = 0.0
    confidence_level: str = CONFIDENCE_LOW
    self_verification_passed: bool = False
    runs_completed: int = 0

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
            "runs_completed": self.runs_completed,
        }


@dataclass
class RuntimeSimulationReport:
    report_id: str = ""
    events: List[SimulationEvent] = field(default_factory=list)
    stress_results: List[StressResult] = field(default_factory=list)
    failures: List[FailureScenario] = field(default_factory=list)
    resources: ResourceSample = field(default_factory=ResourceSample)
    score: RuntimeScore = field(default_factory=RuntimeScore)
    findings: List[RuntimeFinding] = field(default_factory=list)
    event_count: int = 0
    failed_event_count: int = 0
    crash_count: int = 0
    leak_detected: bool = False
    startup_ok: bool = False
    self_verification_passed: bool = False
    readiness_status: str = VERDICT_NOT_READY
    verdict: str = VERDICT_NOT_READY
    cache_info: CacheInfo = field(default_factory=CacheInfo)
    provenance: RuntimeProvenance = field(default_factory=RuntimeProvenance)
    metadata: Dict[str, Any] = field(default_factory=dict)
    is_empty: bool = True

    def to_dict(self) -> Dict[str, Any]:
        return {
            "report_id": self.report_id,
            "events": [e.to_dict() for e in self.events],
            "stress_results": [s.to_dict() for s in self.stress_results],
            "failures": [f.to_dict() for f in self.failures],
            "resources": self.resources.to_dict(),
            "score": self.score.to_dict(),
            "findings": [f.to_dict() for f in self.findings],
            "event_count": self.event_count,
            "failed_event_count": self.failed_event_count,
            "crash_count": self.crash_count,
            "leak_detected": self.leak_detected,
            "startup_ok": self.startup_ok,
            "self_verification_passed": self.self_verification_passed,
            "readiness_status": self.readiness_status,
            "verdict": self.verdict,
            "cache_info": self.cache_info.to_dict(),
            "provenance": self.provenance.to_dict(),
            "metadata": dict(self.metadata),
            "is_empty": self.is_empty,
        }


__all__ = [
    "SOURCE_STATIC_ANALYSIS", "SOURCE_ARCHITECTURE_COMPLIANCE",
    "SOURCE_PERFORMANCE", "SOURCE_SECURITY", "SOURCE_CODE_REFACTORING",
    "SOURCE_PROJECT_CONTEXT", "ALL_SOURCES",
    "SEVERITY_CRITICAL", "SEVERITY_HIGH", "SEVERITY_MEDIUM", "SEVERITY_LOW", "SEVERITY_INFO",
    "EVT_STARTUP", "EVT_INIT", "EVT_CONFIG", "EVT_DI", "EVT_ROUTER", "EVT_EVENT_REG",
    "EVT_COMMAND", "EVT_CALLBACK", "EVT_MESSAGE", "EVT_FILE", "EVT_MEDIA",
    "EVT_ERROR", "EVT_TIMEOUT", "EVT_BACKGROUND", "EVT_TG_UPDATE", "EVT_TG_INLINE",
    "EVT_NETWORK_FAIL", "EVT_API_FAIL", "EVT_PERM_FAIL", "EVT_MEMORY", "EVT_CPU",
    "EVT_STORAGE", "EVT_CRASH", "EVT_EXCEPTION", "EVT_DEADLOCK", "EVT_INFINITE",
    "EVT_LEAK", "EVT_RECOVER", "EVT_RETRY", "EVT_SHUTDOWN", "EVT_RESTART",
    "ALL_EVENT_TYPES",
    "RULE_NO_RUNTIME_ERROR", "RULE_NO_CRASH", "RULE_NO_FAILURE", "RULE_NO_MEMORY_LEAK",
    "RULE_STARTUP_OK", "RULE_SELF_VERIFICATION", "RULE_QUALITY_PASS",
    "RULE_SUFFICIENT_CONFIDENCE", "ALL_QUALITY_RULES",
    "MIN_RUNTIME_SCORE", "MIN_STABILITY",
    "CACHE_HIT", "CACHE_MISS", "CACHE_DISABLED",
    "CONFIDENCE_HIGH", "CONFIDENCE_MEDIUM", "CONFIDENCE_LOW",
    "CONFIDENCE_HIGH_THRESHOLD", "CONFIDENCE_MEDIUM_THRESHOLD",
    "VERDICT_READY", "VERDICT_READY_WITH_WARNINGS", "VERDICT_NOT_READY", "ALL_VERDICTS",
    "STATUS_PASSED", "STATUS_FAILED", "STATUS_SKIPPED", "STATUS_WARNING",
    "SimulationEvent", "StressResult", "FailureScenario", "ResourceSample",
    "RuntimeScore", "RuntimeFinding", "CacheInfo", "RuntimeProvenance",
    "RuntimeSimulationReport",
]
