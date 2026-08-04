"""
Synchronization Report (Specification 055 — CRITICAL).

Keeps all engines on the same data at the same moment.
State sync, conflict detection/resolution, atomic transactions, recovery.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List


SOURCE_EXECUTION_CONTEXT = "execution_context_report"
SOURCE_ORCHESTRATOR = "engine_orchestrator_report"
SOURCE_ECOSYSTEM = "engine_ecosystem_report"
SOURCE_WORKSPACE = "workspace_management_report"
SOURCE_USER_REQUEST = "user_request"

ALL_SOURCES = (
    SOURCE_EXECUTION_CONTEXT,
    SOURCE_ORCHESTRATOR,
    SOURCE_ECOSYSTEM,
    SOURCE_WORKSPACE,
    SOURCE_USER_REQUEST,
)

SEVERITY_CRITICAL = "critical"
SEVERITY_HIGH = "high"
SEVERITY_MEDIUM = "medium"
SEVERITY_LOW = "low"
SEVERITY_INFO = "info"

DOMAIN_PROJECT = "project_state"
DOMAIN_EXECUTION = "execution_state"
DOMAIN_WORKSPACE = "workspace_state"
DOMAIN_ENGINE = "engine_state"

ALL_DOMAINS = (DOMAIN_PROJECT, DOMAIN_EXECUTION, DOMAIN_WORKSPACE, DOMAIN_ENGINE)

CONFLICT_STATE = "state_conflict"
CONFLICT_VERSION = "version_conflict"
CONFLICT_UPDATE = "update_conflict"

TX_COMMITTED = "committed"
TX_ABORTED = "aborted"
TX_PENDING = "pending"

RULE_SINGLE_STATE = "single_state_per_project"
RULE_NO_LOST_UPDATES = "no_lost_updates"
RULE_CONFLICTS_RESOLVED = "conflicts_resolved"
RULE_ATOMIC_OK = "atomic_transactions_ok"
RULE_CONSISTENT = "consistency_ok"
RULE_SELF_VERIFICATION = "self_verification_passed"
RULE_QUALITY_PASS = "quality_pass"

ALL_QUALITY_RULES = (
    RULE_SINGLE_STATE,
    RULE_NO_LOST_UPDATES,
    RULE_CONFLICTS_RESOLVED,
    RULE_ATOMIC_OK,
    RULE_CONSISTENT,
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
class SyncEvent:
    event_id: str
    domain: str
    key: str
    version: int = 1
    source_engine: str = ""
    timestamp: str = ""
    applied: bool = True

    def to_dict(self) -> Dict[str, Any]:
        return {
            "event_id": self.event_id,
            "domain": self.domain,
            "key": self.key,
            "version": self.version,
            "source_engine": self.source_engine,
            "timestamp": self.timestamp,
            "applied": self.applied,
        }


@dataclass
class ConflictRecord:
    conflict_id: str
    conflict_type: str
    domain: str = ""
    key: str = ""
    versions: List[int] = field(default_factory=list)
    engines: List[str] = field(default_factory=list)
    resolution: str = ""
    resolved: bool = False
    data_lost: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "conflict_id": self.conflict_id,
            "conflict_type": self.conflict_type,
            "domain": self.domain,
            "key": self.key,
            "versions": list(self.versions),
            "engines": list(self.engines),
            "resolution": self.resolution,
            "resolved": self.resolved,
            "data_lost": self.data_lost,
        }


@dataclass
class Transaction:
    tx_id: str
    operations: List[str] = field(default_factory=list)
    status: str = TX_PENDING
    rolled_back: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "tx_id": self.tx_id,
            "operations": list(self.operations),
            "status": self.status,
            "rolled_back": self.rolled_back,
        }


@dataclass
class SyncHealth:
    delay_ms: float = 0.0
    conflict_rate: float = 0.0
    consistency_rate: float = 100.0
    queue_depth: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "delay_ms": self.delay_ms,
            "conflict_rate": self.conflict_rate,
            "consistency_rate": self.consistency_rate,
            "queue_depth": self.queue_depth,
        }


@dataclass
class SyncFinding:
    severity: str
    code: str
    message: str
    affected: str = ""
    resolution_hint: str = ""
    category: str = "synchronization"

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
class SyncProvenance:
    engine_name: str = "synchronization"
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
class SynchronizationReport:
    report_id: str = ""
    events: List[SyncEvent] = field(default_factory=list)
    conflicts: List[ConflictRecord] = field(default_factory=list)
    transactions: List[Transaction] = field(default_factory=list)
    health: SyncHealth = field(default_factory=SyncHealth)
    findings: List[SyncFinding] = field(default_factory=list)
    event_count: int = 0
    conflict_count: int = 0
    unresolved_count: int = 0
    recovered: bool = False
    consistent: bool = True
    self_verification_passed: bool = False
    readiness_status: str = VERDICT_NOT_READY
    verdict: str = VERDICT_NOT_READY
    cache_info: CacheInfo = field(default_factory=CacheInfo)
    provenance: SyncProvenance = field(default_factory=SyncProvenance)
    metadata: Dict[str, Any] = field(default_factory=dict)
    is_empty: bool = True

    def to_dict(self) -> Dict[str, Any]:
        return {
            "report_id": self.report_id,
            "events": [e.to_dict() for e in self.events],
            "conflicts": [c.to_dict() for c in self.conflicts],
            "transactions": [t.to_dict() for t in self.transactions],
            "health": self.health.to_dict(),
            "findings": [f.to_dict() for f in self.findings],
            "event_count": self.event_count,
            "conflict_count": self.conflict_count,
            "unresolved_count": self.unresolved_count,
            "recovered": self.recovered,
            "consistent": self.consistent,
            "self_verification_passed": self.self_verification_passed,
            "readiness_status": self.readiness_status,
            "verdict": self.verdict,
            "cache_info": self.cache_info.to_dict(),
            "provenance": self.provenance.to_dict(),
            "metadata": dict(self.metadata),
            "is_empty": self.is_empty,
        }


__all__ = [
    "SOURCE_EXECUTION_CONTEXT", "SOURCE_ORCHESTRATOR", "SOURCE_ECOSYSTEM",
    "SOURCE_WORKSPACE", "SOURCE_USER_REQUEST", "ALL_SOURCES",
    "SEVERITY_CRITICAL", "SEVERITY_HIGH", "SEVERITY_MEDIUM", "SEVERITY_LOW", "SEVERITY_INFO",
    "DOMAIN_PROJECT", "DOMAIN_EXECUTION", "DOMAIN_WORKSPACE", "DOMAIN_ENGINE", "ALL_DOMAINS",
    "CONFLICT_STATE", "CONFLICT_VERSION", "CONFLICT_UPDATE",
    "TX_COMMITTED", "TX_ABORTED", "TX_PENDING",
    "RULE_SINGLE_STATE", "RULE_NO_LOST_UPDATES", "RULE_CONFLICTS_RESOLVED",
    "RULE_ATOMIC_OK", "RULE_CONSISTENT", "RULE_SELF_VERIFICATION", "RULE_QUALITY_PASS",
    "ALL_QUALITY_RULES",
    "CACHE_HIT", "CACHE_MISS", "CACHE_DISABLED",
    "CONFIDENCE_HIGH", "CONFIDENCE_MEDIUM", "CONFIDENCE_LOW",
    "CONFIDENCE_HIGH_THRESHOLD", "CONFIDENCE_MEDIUM_THRESHOLD",
    "VERDICT_READY", "VERDICT_READY_WITH_WARNINGS", "VERDICT_NOT_READY", "ALL_VERDICTS",
    "SyncEvent", "ConflictRecord", "Transaction", "SyncHealth",
    "SyncFinding", "CacheInfo", "SyncProvenance", "SynchronizationReport",
]
