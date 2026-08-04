"""
System Monitoring Report (Specification 057 — CRITICAL).

Real-time monitoring of the whole platform: resources, engines, health,
performance, anomalies, alerts, history and trends.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List


SOURCE_RESOURCE = "resource_management_report"
SOURCE_SYNC = "synchronization_report"
SOURCE_ORCHESTRATOR = "engine_orchestrator_report"
SOURCE_ECOSYSTEM = "engine_ecosystem_report"
SOURCE_EXECUTION_CONTEXT = "execution_context_report"
SOURCE_WORKSPACE = "workspace_management_report"
SOURCE_USER_REQUEST = "user_request"

ALL_SOURCES = (
    SOURCE_RESOURCE,
    SOURCE_SYNC,
    SOURCE_ORCHESTRATOR,
    SOURCE_ECOSYSTEM,
    SOURCE_EXECUTION_CONTEXT,
    SOURCE_WORKSPACE,
    SOURCE_USER_REQUEST,
)

SEVERITY_CRITICAL = "critical"
SEVERITY_HIGH = "high"
SEVERITY_MEDIUM = "medium"
SEVERITY_LOW = "low"
SEVERITY_INFO = "info"

# Engine lifecycle states
STATE_RUNNING = "running"
STATE_WAITING = "waiting"
STATE_STOPPED = "stopped"
STATE_FAILED = "failed"
STATE_COMPLETED = "completed"

ALL_ENGINE_STATES = (
    STATE_RUNNING, STATE_WAITING, STATE_STOPPED, STATE_FAILED, STATE_COMPLETED,
)

# Metric kinds
METRIC_CPU = "cpu"
METRIC_RAM = "ram"
METRIC_DISK = "disk"
METRIC_THREADS = "threads"
METRIC_NETWORK = "network"
METRIC_WORKSPACE = "workspace"
METRIC_ENGINES = "engines"

ALL_METRICS = (
    METRIC_CPU, METRIC_RAM, METRIC_DISK, METRIC_THREADS,
    METRIC_NETWORK, METRIC_WORKSPACE, METRIC_ENGINES,
)

# Anomaly kinds
ANOMALY_SLOW_ENGINE = "slow_engine"
ANOMALY_UNEXPECTED_DELAY = "unexpected_delay"
ANOMALY_RESOURCE_SPIKE = "resource_spike"
ANOMALY_EXECUTION_LOOP = "execution_loop"

ALL_ANOMALIES = (
    ANOMALY_SLOW_ENGINE, ANOMALY_UNEXPECTED_DELAY,
    ANOMALY_RESOURCE_SPIKE, ANOMALY_EXECUTION_LOOP,
)

# Alert kinds
ALERT_ENGINE_FAILURE = "engine_failure"
ALERT_HIGH_MEMORY = "high_memory"
ALERT_HIGH_CPU = "high_cpu"
ALERT_SYNC_FAILURE = "synchronization_failure"
ALERT_WORKSPACE_FAILURE = "workspace_failure"

ALL_ALERTS = (
    ALERT_ENGINE_FAILURE, ALERT_HIGH_MEMORY, ALERT_HIGH_CPU,
    ALERT_SYNC_FAILURE, ALERT_WORKSPACE_FAILURE,
)

RULE_CRITICAL_BEFORE_IMPACT = "critical_problems_detected_before_impact"
RULE_HEALTH_TRACKED = "health_tracked"
RULE_ANOMALIES_DETECTED = "anomalies_detected"
RULE_ALERTS_ISSUED = "alerts_issued"
RULE_SELF_VERIFICATION = "self_verification_passed"
RULE_QUALITY_PASS = "quality_pass"

ALL_QUALITY_RULES = (
    RULE_CRITICAL_BEFORE_IMPACT,
    RULE_HEALTH_TRACKED,
    RULE_ANOMALIES_DETECTED,
    RULE_ALERTS_ISSUED,
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

TREND_IMPROVING = "improving"
TREND_STABLE = "stable"
TREND_DEGRADING = "degrading"


@dataclass
class MetricSample:
    name: str
    value: float = 0.0
    unit: str = ""
    threshold_warn: float = 0.0
    threshold_crit: float = 0.0
    status: str = "ok"  # ok | warn | critical

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "value": self.value,
            "unit": self.unit,
            "threshold_warn": self.threshold_warn,
            "threshold_crit": self.threshold_crit,
            "status": self.status,
        }


@dataclass
class EngineStatus:
    engine_id: str
    state: str = STATE_WAITING
    execution_time_ms: float = 0.0
    response_time_ms: float = 0.0
    queue_time_ms: float = 0.0
    health_score: float = 1.0
    last_error: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "engine_id": self.engine_id,
            "state": self.state,
            "execution_time_ms": self.execution_time_ms,
            "response_time_ms": self.response_time_ms,
            "queue_time_ms": self.queue_time_ms,
            "health_score": self.health_score,
            "last_error": self.last_error,
        }


@dataclass
class HealthSnapshot:
    overall_score: float = 1.0
    availability: float = 1.0
    reliability: float = 1.0
    healthy_engines: int = 0
    unhealthy_engines: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "overall_score": self.overall_score,
            "availability": self.availability,
            "reliability": self.reliability,
            "healthy_engines": self.healthy_engines,
            "unhealthy_engines": self.unhealthy_engines,
        }


@dataclass
class PerformanceSnapshot:
    avg_execution_time_ms: float = 0.0
    avg_response_time_ms: float = 0.0
    avg_queue_time_ms: float = 0.0
    max_execution_time_ms: float = 0.0
    slow_engine_count: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "avg_execution_time_ms": self.avg_execution_time_ms,
            "avg_response_time_ms": self.avg_response_time_ms,
            "avg_queue_time_ms": self.avg_queue_time_ms,
            "max_execution_time_ms": self.max_execution_time_ms,
            "slow_engine_count": self.slow_engine_count,
        }


@dataclass
class AnomalyRecord:
    anomaly_id: str
    kind: str
    engine_id: str = ""
    severity: str = SEVERITY_MEDIUM
    message: str = ""
    metric_value: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "anomaly_id": self.anomaly_id,
            "kind": self.kind,
            "engine_id": self.engine_id,
            "severity": self.severity,
            "message": self.message,
            "metric_value": self.metric_value,
        }


@dataclass
class AlertRecord:
    alert_id: str
    kind: str
    severity: str = SEVERITY_HIGH
    message: str = ""
    source: str = ""
    acknowledged: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "alert_id": self.alert_id,
            "kind": self.kind,
            "severity": self.severity,
            "message": self.message,
            "source": self.source,
            "acknowledged": self.acknowledged,
        }


@dataclass
class HistoryEntry:
    timestamp: str
    event_type: str  # performance | failure | alert | state_change
    summary: str = ""
    details: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "timestamp": self.timestamp,
            "event_type": self.event_type,
            "summary": self.summary,
            "details": dict(self.details),
        }


@dataclass
class TrendReport:
    direction: str = TREND_STABLE  # improving | stable | degrading
    performance_delta: float = 0.0
    failure_rate_delta: float = 0.0
    health_delta: float = 0.0
    notes: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "direction": self.direction,
            "performance_delta": self.performance_delta,
            "failure_rate_delta": self.failure_rate_delta,
            "health_delta": self.health_delta,
            "notes": self.notes,
        }


@dataclass
class MonitoringFinding:
    severity: str
    code: str
    message: str
    affected: str = ""
    resolution_hint: str = ""
    category: str = "monitoring"

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
class MonitoringProvenance:
    engine_name: str = "system_monitoring"
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
class SystemMonitoringReport:
    report_id: str = ""
    metrics: List[MetricSample] = field(default_factory=list)
    engine_statuses: List[EngineStatus] = field(default_factory=list)
    health: HealthSnapshot = field(default_factory=HealthSnapshot)
    performance: PerformanceSnapshot = field(default_factory=PerformanceSnapshot)
    anomalies: List[AnomalyRecord] = field(default_factory=list)
    alerts: List[AlertRecord] = field(default_factory=list)
    history: List[HistoryEntry] = field(default_factory=list)
    trend: TrendReport = field(default_factory=TrendReport)
    findings: List[MonitoringFinding] = field(default_factory=list)
    engine_count: int = 0
    anomaly_count: int = 0
    alert_count: int = 0
    critical_alert_count: int = 0
    self_verification_passed: bool = False
    monitoring_self_ok: bool = False
    readiness_status: str = VERDICT_NOT_READY
    verdict: str = VERDICT_NOT_READY
    cache_info: CacheInfo = field(default_factory=CacheInfo)
    provenance: MonitoringProvenance = field(default_factory=MonitoringProvenance)
    metadata: Dict[str, Any] = field(default_factory=dict)
    is_empty: bool = True

    def to_dict(self) -> Dict[str, Any]:
        return {
            "report_id": self.report_id,
            "metrics": [m.to_dict() for m in self.metrics],
            "engine_statuses": [e.to_dict() for e in self.engine_statuses],
            "health": self.health.to_dict(),
            "performance": self.performance.to_dict(),
            "anomalies": [a.to_dict() for a in self.anomalies],
            "alerts": [a.to_dict() for a in self.alerts],
            "history": [h.to_dict() for h in self.history],
            "trend": self.trend.to_dict(),
            "findings": [f.to_dict() for f in self.findings],
            "engine_count": self.engine_count,
            "anomaly_count": self.anomaly_count,
            "alert_count": self.alert_count,
            "critical_alert_count": self.critical_alert_count,
            "self_verification_passed": self.self_verification_passed,
            "monitoring_self_ok": self.monitoring_self_ok,
            "readiness_status": self.readiness_status,
            "verdict": self.verdict,
            "cache_info": self.cache_info.to_dict(),
            "provenance": self.provenance.to_dict(),
            "metadata": dict(self.metadata),
            "is_empty": self.is_empty,
        }


__all__ = [
    "SOURCE_RESOURCE", "SOURCE_SYNC", "SOURCE_ORCHESTRATOR", "SOURCE_ECOSYSTEM",
    "SOURCE_EXECUTION_CONTEXT", "SOURCE_WORKSPACE", "SOURCE_USER_REQUEST", "ALL_SOURCES",
    "SEVERITY_CRITICAL", "SEVERITY_HIGH", "SEVERITY_MEDIUM", "SEVERITY_LOW", "SEVERITY_INFO",
    "STATE_RUNNING", "STATE_WAITING", "STATE_STOPPED", "STATE_FAILED", "STATE_COMPLETED",
    "ALL_ENGINE_STATES",
    "METRIC_CPU", "METRIC_RAM", "METRIC_DISK", "METRIC_THREADS",
    "METRIC_NETWORK", "METRIC_WORKSPACE", "METRIC_ENGINES", "ALL_METRICS",
    "ANOMALY_SLOW_ENGINE", "ANOMALY_UNEXPECTED_DELAY", "ANOMALY_RESOURCE_SPIKE",
    "ANOMALY_EXECUTION_LOOP", "ALL_ANOMALIES",
    "ALERT_ENGINE_FAILURE", "ALERT_HIGH_MEMORY", "ALERT_HIGH_CPU",
    "ALERT_SYNC_FAILURE", "ALERT_WORKSPACE_FAILURE", "ALL_ALERTS",
    "RULE_CRITICAL_BEFORE_IMPACT", "RULE_HEALTH_TRACKED", "RULE_ANOMALIES_DETECTED",
    "RULE_ALERTS_ISSUED", "RULE_SELF_VERIFICATION", "RULE_QUALITY_PASS", "ALL_QUALITY_RULES",
    "CACHE_HIT", "CACHE_MISS", "CACHE_DISABLED",
    "CONFIDENCE_HIGH", "CONFIDENCE_MEDIUM", "CONFIDENCE_LOW",
    "CONFIDENCE_HIGH_THRESHOLD", "CONFIDENCE_MEDIUM_THRESHOLD",
    "VERDICT_READY", "VERDICT_READY_WITH_WARNINGS", "VERDICT_NOT_READY", "ALL_VERDICTS",
    "TREND_IMPROVING", "TREND_STABLE", "TREND_DEGRADING",
    "MetricSample", "EngineStatus", "HealthSnapshot", "PerformanceSnapshot",
    "AnomalyRecord", "AlertRecord", "HistoryEntry", "TrendReport",
    "MonitoringFinding", "CacheInfo", "MonitoringProvenance", "SystemMonitoringReport",
]
