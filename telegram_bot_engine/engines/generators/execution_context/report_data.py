"""
Execution Context Report (Specification 054 — CRITICAL).

Unified execution context shared by all engines. One active context per project.
Versioned, locked, validated, synchronized and recoverable.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List


SOURCE_ORCHESTRATOR = "engine_orchestrator_report"
SOURCE_ECOSYSTEM = "engine_ecosystem_report"
SOURCE_WORKSPACE = "workspace_management_report"
SOURCE_PROJECT_CONTEXT = "project_context_report"
SOURCE_USER_REQUEST = "user_request"

ALL_SOURCES = (
    SOURCE_ORCHESTRATOR,
    SOURCE_ECOSYSTEM,
    SOURCE_WORKSPACE,
    SOURCE_PROJECT_CONTEXT,
    SOURCE_USER_REQUEST,
)

SEVERITY_CRITICAL = "critical"
SEVERITY_HIGH = "high"
SEVERITY_MEDIUM = "medium"
SEVERITY_LOW = "low"
SEVERITY_INFO = "info"

# Context status
CTX_ACTIVE = "active"
CTX_LOCKED = "locked"
CTX_SUSPENDED = "suspended"
CTX_RECOVERED = "recovered"
CTX_CLOSED = "closed"

RULE_SINGLE_ACTIVE = "single_active_context"
RULE_NO_OUTSIDE_CONTEXT = "no_work_outside_context"
RULE_ISOLATION_OK = "context_isolation_ok"
RULE_VALID_DATA = "context_data_valid"
RULE_SELF_VERIFICATION = "self_verification_passed"
RULE_QUALITY_PASS = "quality_pass"

ALL_QUALITY_RULES = (
    RULE_SINGLE_ACTIVE,
    RULE_NO_OUTSIDE_CONTEXT,
    RULE_ISOLATION_OK,
    RULE_VALID_DATA,
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

STATUS_OK = "ok"
STATUS_FAILED = "failed"
STATUS_LOCKED = "locked"
STATUS_RECOVERED = "recovered"


@dataclass
class ContextVersion:
    version: int
    created_at: str = ""
    change_summary: str = ""
    author_engine: str = ""
    snapshot_keys: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "version": self.version,
            "created_at": self.created_at,
            "change_summary": self.change_summary,
            "author_engine": self.author_engine,
            "snapshot_keys": list(self.snapshot_keys),
        }


@dataclass
class ContextLock:
    lock_id: str
    key: str
    holder_engine: str = ""
    acquired_at: str = ""
    released: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "lock_id": self.lock_id,
            "key": self.key,
            "holder_engine": self.holder_engine,
            "acquired_at": self.acquired_at,
            "released": self.released,
        }


@dataclass
class ContextChange:
    change_id: str
    key: str
    action: str  # set|update|delete
    version: int = 0
    engine_id: str = ""
    timestamp: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "change_id": self.change_id,
            "key": self.key,
            "action": self.action,
            "version": self.version,
            "engine_id": self.engine_id,
            "timestamp": self.timestamp,
        }


@dataclass
class ValidationIssue:
    issue_id: str
    code: str
    message: str
    severity: str = SEVERITY_MEDIUM
    key: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "issue_id": self.issue_id,
            "code": self.code,
            "message": self.message,
            "severity": self.severity,
            "key": self.key,
        }


@dataclass
class ContextFinding:
    severity: str
    code: str
    message: str
    affected: str = ""
    resolution_hint: str = ""
    category: str = "context"

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
class ContextProvenance:
    engine_name: str = "execution_context"
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
class ExecutionContextReport:
    report_id: str = ""
    context_id: str = ""
    project_id: str = ""
    status: str = CTX_ACTIVE
    version: int = 1
    versions: List[ContextVersion] = field(default_factory=list)
    locks: List[ContextLock] = field(default_factory=list)
    changes: List[ContextChange] = field(default_factory=list)
    validation_issues: List[ValidationIssue] = field(default_factory=list)
    shared_keys: List[str] = field(default_factory=list)
    findings: List[ContextFinding] = field(default_factory=list)
    active_count: int = 0
    isolated: bool = True
    recovered: bool = False
    self_verification_passed: bool = False
    readiness_status: str = VERDICT_NOT_READY
    verdict: str = VERDICT_NOT_READY
    cache_info: CacheInfo = field(default_factory=CacheInfo)
    provenance: ContextProvenance = field(default_factory=ContextProvenance)
    metadata: Dict[str, Any] = field(default_factory=dict)
    is_empty: bool = True

    def to_dict(self) -> Dict[str, Any]:
        return {
            "report_id": self.report_id,
            "context_id": self.context_id,
            "project_id": self.project_id,
            "status": self.status,
            "version": self.version,
            "versions": [v.to_dict() for v in self.versions],
            "locks": [l.to_dict() for l in self.locks],
            "changes": [c.to_dict() for c in self.changes],
            "validation_issues": [i.to_dict() for i in self.validation_issues],
            "shared_keys": list(self.shared_keys),
            "findings": [f.to_dict() for f in self.findings],
            "active_count": self.active_count,
            "isolated": self.isolated,
            "recovered": self.recovered,
            "self_verification_passed": self.self_verification_passed,
            "readiness_status": self.readiness_status,
            "verdict": self.verdict,
            "cache_info": self.cache_info.to_dict(),
            "provenance": self.provenance.to_dict(),
            "metadata": dict(self.metadata),
            "is_empty": self.is_empty,
        }


__all__ = [
    "SOURCE_ORCHESTRATOR", "SOURCE_ECOSYSTEM", "SOURCE_WORKSPACE",
    "SOURCE_PROJECT_CONTEXT", "SOURCE_USER_REQUEST", "ALL_SOURCES",
    "SEVERITY_CRITICAL", "SEVERITY_HIGH", "SEVERITY_MEDIUM", "SEVERITY_LOW", "SEVERITY_INFO",
    "CTX_ACTIVE", "CTX_LOCKED", "CTX_SUSPENDED", "CTX_RECOVERED", "CTX_CLOSED",
    "RULE_SINGLE_ACTIVE", "RULE_NO_OUTSIDE_CONTEXT", "RULE_ISOLATION_OK",
    "RULE_VALID_DATA", "RULE_SELF_VERIFICATION", "RULE_QUALITY_PASS",
    "ALL_QUALITY_RULES",
    "CACHE_HIT", "CACHE_MISS", "CACHE_DISABLED",
    "CONFIDENCE_HIGH", "CONFIDENCE_MEDIUM", "CONFIDENCE_LOW",
    "CONFIDENCE_HIGH_THRESHOLD", "CONFIDENCE_MEDIUM_THRESHOLD",
    "VERDICT_READY", "VERDICT_READY_WITH_WARNINGS", "VERDICT_NOT_READY", "ALL_VERDICTS",
    "STATUS_OK", "STATUS_FAILED", "STATUS_LOCKED", "STATUS_RECOVERED",
    "ContextVersion", "ContextLock", "ContextChange", "ValidationIssue",
    "ContextFinding", "CacheInfo", "ContextProvenance", "ExecutionContextReport",
]
