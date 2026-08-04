"""
Central Logging & Audit Report (Specification 058 — CRITICAL).

Single authoritative log sink for the platform. No engine may write
logs outside this engine. Supports categories, levels, audit trail,
immutability, search, rotation, sensitive-data redaction and integrity.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List


SOURCE_MONITORING = "system_monitoring_report"
SOURCE_RESOURCE = "resource_management_report"
SOURCE_SYNC = "synchronization_report"
SOURCE_ORCHESTRATOR = "engine_orchestrator_report"
SOURCE_EXECUTION_CONTEXT = "execution_context_report"
SOURCE_WORKSPACE = "workspace_management_report"
SOURCE_USER_REQUEST = "user_request"

ALL_SOURCES = (
    SOURCE_MONITORING,
    SOURCE_RESOURCE,
    SOURCE_SYNC,
    SOURCE_ORCHESTRATOR,
    SOURCE_EXECUTION_CONTEXT,
    SOURCE_WORKSPACE,
    SOURCE_USER_REQUEST,
)

# Log categories
CAT_EXECUTION = "execution"
CAT_ENGINE = "engine"
CAT_SECURITY = "security"
CAT_GIT = "git"
CAT_WORKSPACE = "workspace"
CAT_REPOSITORY = "repository"
CAT_PERFORMANCE = "performance"
CAT_SYSTEM = "system"

ALL_CATEGORIES = (
    CAT_EXECUTION, CAT_ENGINE, CAT_SECURITY, CAT_GIT,
    CAT_WORKSPACE, CAT_REPOSITORY, CAT_PERFORMANCE, CAT_SYSTEM,
)

# Log levels
LEVEL_DEBUG = "DEBUG"
LEVEL_INFO = "INFO"
LEVEL_WARNING = "WARNING"
LEVEL_ERROR = "ERROR"
LEVEL_CRITICAL = "CRITICAL"

ALL_LEVELS = (
    LEVEL_DEBUG, LEVEL_INFO, LEVEL_WARNING, LEVEL_ERROR, LEVEL_CRITICAL,
)

LEVEL_RANK = {
    LEVEL_DEBUG: 10,
    LEVEL_INFO: 20,
    LEVEL_WARNING: 30,
    LEVEL_ERROR: 40,
    LEVEL_CRITICAL: 50,
}

SEVERITY_CRITICAL = "critical"
SEVERITY_HIGH = "high"
SEVERITY_MEDIUM = "medium"
SEVERITY_LOW = "low"
SEVERITY_INFO = "info"

RULE_CENTRAL_ONLY = "no_external_engine_logs"
RULE_IMMUTABLE = "logs_immutable"
RULE_SENSITIVE_REDACTED = "sensitive_data_redacted"
RULE_INTEGRITY = "integrity_verified"
RULE_SELF_VERIFICATION = "self_verification_passed"
RULE_QUALITY_PASS = "quality_pass"

ALL_QUALITY_RULES = (
    RULE_CENTRAL_ONLY,
    RULE_IMMUTABLE,
    RULE_SENSITIVE_REDACTED,
    RULE_INTEGRITY,
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

# Sensitive patterns to redact
SENSITIVE_KEYS = (
    "password", "passwd", "secret", "api_key", "apikey", "token",
    "access_token", "refresh_token", "private_key", "credential",
    "auth", "authorization", "bearer",
)


@dataclass
class LogEntry:
    log_id: str
    timestamp: str
    level: str = LEVEL_INFO
    category: str = CAT_SYSTEM
    engine_id: str = ""
    user_id: str = ""
    project_id: str = ""
    action: str = ""
    message: str = ""
    result: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)
    immutable: bool = True
    checksum: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "log_id": self.log_id,
            "timestamp": self.timestamp,
            "level": self.level,
            "category": self.category,
            "engine_id": self.engine_id,
            "user_id": self.user_id,
            "project_id": self.project_id,
            "action": self.action,
            "message": self.message,
            "result": self.result,
            "metadata": dict(self.metadata),
            "immutable": self.immutable,
            "checksum": self.checksum,
        }


@dataclass
class AuditRecord:
    audit_id: str
    timestamp: str
    user_id: str = ""
    engine_id: str = ""
    action: str = ""
    result: str = ""
    project_id: str = ""
    details: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "audit_id": self.audit_id,
            "timestamp": self.timestamp,
            "user_id": self.user_id,
            "engine_id": self.engine_id,
            "action": self.action,
            "result": self.result,
            "project_id": self.project_id,
            "details": dict(self.details),
        }


@dataclass
class SearchQuery:
    engine_id: str = ""
    level: str = ""
    category: str = ""
    user_id: str = ""
    project_id: str = ""
    time_from: str = ""
    time_to: str = ""
    text: str = ""
    error_type: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "engine_id": self.engine_id,
            "level": self.level,
            "category": self.category,
            "user_id": self.user_id,
            "project_id": self.project_id,
            "time_from": self.time_from,
            "time_to": self.time_to,
            "text": self.text,
            "error_type": self.error_type,
        }


@dataclass
class SearchHit:
    log_id: str
    score: float = 1.0
    snippet: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "log_id": self.log_id,
            "score": self.score,
            "snippet": self.snippet,
        }


@dataclass
class SearchReport:
    query: SearchQuery = field(default_factory=SearchQuery)
    hits: List[SearchHit] = field(default_factory=list)
    total: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "query": self.query.to_dict(),
            "hits": [h.to_dict() for h in self.hits],
            "total": self.total,
        }


@dataclass
class ArchiveRecord:
    archive_id: str
    created_at: str
    entry_count: int = 0
    size_bytes: int = 0
    compressed: bool = True
    path: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "archive_id": self.archive_id,
            "created_at": self.created_at,
            "entry_count": self.entry_count,
            "size_bytes": self.size_bytes,
            "compressed": self.compressed,
            "path": self.path,
        }


@dataclass
class IntegrityReport:
    verified: bool = False
    total_entries: int = 0
    valid_checksums: int = 0
    tampered: int = 0
    missing_checksums: int = 0
    message: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "verified": self.verified,
            "total_entries": self.total_entries,
            "valid_checksums": self.valid_checksums,
            "tampered": self.tampered,
            "missing_checksums": self.missing_checksums,
            "message": self.message,
        }


@dataclass
class LoggingFinding:
    severity: str
    code: str
    message: str
    affected: str = ""
    resolution_hint: str = ""
    category: str = "logging"

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
class LoggingProvenance:
    engine_name: str = "central_logging"
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
class CentralLoggingReport:
    report_id: str = ""
    entries: List[LogEntry] = field(default_factory=list)
    audit_trail: List[AuditRecord] = field(default_factory=list)
    search: SearchReport = field(default_factory=SearchReport)
    integrity: IntegrityReport = field(default_factory=IntegrityReport)
    archives: List[ArchiveRecord] = field(default_factory=list)
    findings: List[LoggingFinding] = field(default_factory=list)
    entry_count: int = 0
    audit_count: int = 0
    redacted_count: int = 0
    rotated: bool = False
    external_log_violations: int = 0
    self_verification_passed: bool = False
    readiness_status: str = VERDICT_NOT_READY
    verdict: str = VERDICT_NOT_READY
    cache_info: CacheInfo = field(default_factory=CacheInfo)
    provenance: LoggingProvenance = field(default_factory=LoggingProvenance)
    metadata: Dict[str, Any] = field(default_factory=dict)
    is_empty: bool = True

    def to_dict(self) -> Dict[str, Any]:
        return {
            "report_id": self.report_id,
            "entries": [e.to_dict() for e in self.entries],
            "audit_trail": [a.to_dict() for a in self.audit_trail],
            "search": self.search.to_dict(),
            "integrity": self.integrity.to_dict(),
            "archives": [a.to_dict() for a in self.archives],
            "findings": [f.to_dict() for f in self.findings],
            "entry_count": self.entry_count,
            "audit_count": self.audit_count,
            "redacted_count": self.redacted_count,
            "rotated": self.rotated,
            "external_log_violations": self.external_log_violations,
            "self_verification_passed": self.self_verification_passed,
            "readiness_status": self.readiness_status,
            "verdict": self.verdict,
            "cache_info": self.cache_info.to_dict(),
            "provenance": self.provenance.to_dict(),
            "metadata": dict(self.metadata),
            "is_empty": self.is_empty,
        }


__all__ = [
    "SOURCE_MONITORING", "SOURCE_RESOURCE", "SOURCE_SYNC", "SOURCE_ORCHESTRATOR",
    "SOURCE_EXECUTION_CONTEXT", "SOURCE_WORKSPACE", "SOURCE_USER_REQUEST", "ALL_SOURCES",
    "CAT_EXECUTION", "CAT_ENGINE", "CAT_SECURITY", "CAT_GIT", "CAT_WORKSPACE",
    "CAT_REPOSITORY", "CAT_PERFORMANCE", "CAT_SYSTEM", "ALL_CATEGORIES",
    "LEVEL_DEBUG", "LEVEL_INFO", "LEVEL_WARNING", "LEVEL_ERROR", "LEVEL_CRITICAL",
    "ALL_LEVELS", "LEVEL_RANK",
    "SEVERITY_CRITICAL", "SEVERITY_HIGH", "SEVERITY_MEDIUM", "SEVERITY_LOW", "SEVERITY_INFO",
    "RULE_CENTRAL_ONLY", "RULE_IMMUTABLE", "RULE_SENSITIVE_REDACTED", "RULE_INTEGRITY",
    "RULE_SELF_VERIFICATION", "RULE_QUALITY_PASS", "ALL_QUALITY_RULES",
    "CACHE_HIT", "CACHE_MISS", "CACHE_DISABLED",
    "CONFIDENCE_HIGH", "CONFIDENCE_MEDIUM", "CONFIDENCE_LOW",
    "CONFIDENCE_HIGH_THRESHOLD", "CONFIDENCE_MEDIUM_THRESHOLD",
    "VERDICT_READY", "VERDICT_READY_WITH_WARNINGS", "VERDICT_NOT_READY", "ALL_VERDICTS",
    "SENSITIVE_KEYS",
    "LogEntry", "AuditRecord", "SearchQuery", "SearchHit", "SearchReport",
    "ArchiveRecord", "IntegrityReport", "LoggingFinding", "CacheInfo",
    "LoggingProvenance", "CentralLoggingReport",
]
