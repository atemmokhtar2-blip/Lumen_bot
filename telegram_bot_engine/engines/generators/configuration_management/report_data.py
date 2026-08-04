"""
Configuration Management Report (Specification 059 — CRITICAL).

Central configuration registry for the platform and all engines.
Validation, defaults, dynamic updates, versioning, rollback,
sync, protection, backup and recovery.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List


SOURCE_LOGGING = "central_logging_report"
SOURCE_MONITORING = "system_monitoring_report"
SOURCE_RESOURCE = "resource_management_report"
SOURCE_ENV = "environment_config_report"
SOURCE_WORKSPACE = "workspace_management_report"
SOURCE_USER_REQUEST = "user_request"

ALL_SOURCES = (
    SOURCE_LOGGING,
    SOURCE_MONITORING,
    SOURCE_RESOURCE,
    SOURCE_ENV,
    SOURCE_WORKSPACE,
    SOURCE_USER_REQUEST,
)

SEVERITY_CRITICAL = "critical"
SEVERITY_HIGH = "high"
SEVERITY_MEDIUM = "medium"
SEVERITY_LOW = "low"
SEVERITY_INFO = "info"

SCOPE_PLATFORM = "platform"
SCOPE_ENGINE = "engine"
SCOPE_WORKSPACE = "workspace"
SCOPE_ENVIRONMENT = "environment"

ALL_SCOPES = (SCOPE_PLATFORM, SCOPE_ENGINE, SCOPE_WORKSPACE, SCOPE_ENVIRONMENT)

# Validation issue kinds
ISSUE_MISSING = "missing"
ISSUE_INVALID = "invalid"
ISSUE_DUPLICATE = "duplicate"
ISSUE_UNSUPPORTED = "unsupported"

ALL_ISSUE_KINDS = (ISSUE_MISSING, ISSUE_INVALID, ISSUE_DUPLICATE, ISSUE_UNSUPPORTED)

RULE_CENTRAL_ONLY = "no_external_engine_config"
RULE_VALIDATED = "all_config_validated"
RULE_VERSIONED = "changes_versioned"
RULE_PROTECTED = "sensitive_config_protected"
RULE_SELF_VERIFICATION = "self_verification_passed"
RULE_QUALITY_PASS = "quality_pass"

ALL_QUALITY_RULES = (
    RULE_CENTRAL_ONLY,
    RULE_VALIDATED,
    RULE_VERSIONED,
    RULE_PROTECTED,
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

SENSITIVE_KEYS = (
    "password", "secret", "api_key", "token", "private_key",
    "credential", "access_key", "auth",
)


@dataclass
class ConfigEntry:
    key: str
    value: Any = None
    scope: str = SCOPE_PLATFORM
    engine_id: str = ""
    default: Any = None
    sensitive: bool = False
    version: int = 1
    description: str = ""

    def to_dict(self) -> Dict[str, Any]:
        val = "***PROTECTED***" if self.sensitive else self.value
        return {
            "key": self.key,
            "value": val,
            "scope": self.scope,
            "engine_id": self.engine_id,
            "default": self.default if not self.sensitive else "***PROTECTED***",
            "sensitive": self.sensitive,
            "version": self.version,
            "description": self.description,
        }


@dataclass
class ValidationIssue:
    issue_id: str
    kind: str
    key: str
    message: str
    severity: str = SEVERITY_MEDIUM
    scope: str = SCOPE_PLATFORM

    def to_dict(self) -> Dict[str, Any]:
        return {
            "issue_id": self.issue_id,
            "kind": self.kind,
            "key": self.key,
            "message": self.message,
            "severity": self.severity,
            "scope": self.scope,
        }


@dataclass
class ConfigVersion:
    version: int
    created_at: str
    author: str = "system"
    change_summary: str = ""
    entry_count: int = 0
    snapshot_keys: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "version": self.version,
            "created_at": self.created_at,
            "author": self.author,
            "change_summary": self.change_summary,
            "entry_count": self.entry_count,
            "snapshot_keys": list(self.snapshot_keys),
        }


@dataclass
class BackupRecord:
    backup_id: str
    created_at: str
    version: int = 0
    entry_count: int = 0
    size_estimate: int = 0
    path: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "backup_id": self.backup_id,
            "created_at": self.created_at,
            "version": self.version,
            "entry_count": self.entry_count,
            "size_estimate": self.size_estimate,
            "path": self.path,
        }


@dataclass
class RecoveryRecord:
    recovery_id: str
    timestamp: str
    from_version: int = 0
    to_version: int = 0
    success: bool = True
    message: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "recovery_id": self.recovery_id,
            "timestamp": self.timestamp,
            "from_version": self.from_version,
            "to_version": self.to_version,
            "success": self.success,
            "message": self.message,
        }


@dataclass
class ConfigChangeLog:
    change_id: str
    timestamp: str
    action: str  # set | delete | rollback | update | backup | recover
    key: str = ""
    actor: str = "system"
    details: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "change_id": self.change_id,
            "timestamp": self.timestamp,
            "action": self.action,
            "key": self.key,
            "actor": self.actor,
            "details": self.details,
        }


@dataclass
class ConfigFinding:
    severity: str
    code: str
    message: str
    affected: str = ""
    resolution_hint: str = ""
    category: str = "configuration"

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
class ConfigProvenance:
    engine_name: str = "configuration_management"
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
class ConfigurationManagementReport:
    report_id: str = ""
    entries: List[ConfigEntry] = field(default_factory=list)
    issues: List[ValidationIssue] = field(default_factory=list)
    versions: List[ConfigVersion] = field(default_factory=list)
    backups: List[BackupRecord] = field(default_factory=list)
    recoveries: List[RecoveryRecord] = field(default_factory=list)
    change_log: List[ConfigChangeLog] = field(default_factory=list)
    findings: List[ConfigFinding] = field(default_factory=list)
    entry_count: int = 0
    issue_count: int = 0
    current_version: int = 0
    synced: bool = False
    external_config_violations: int = 0
    protected_keys: int = 0
    self_verification_passed: bool = False
    readiness_status: str = VERDICT_NOT_READY
    verdict: str = VERDICT_NOT_READY
    cache_info: CacheInfo = field(default_factory=CacheInfo)
    provenance: ConfigProvenance = field(default_factory=ConfigProvenance)
    metadata: Dict[str, Any] = field(default_factory=dict)
    is_empty: bool = True

    def to_dict(self) -> Dict[str, Any]:
        return {
            "report_id": self.report_id,
            "entries": [e.to_dict() for e in self.entries],
            "issues": [i.to_dict() for i in self.issues],
            "versions": [v.to_dict() for v in self.versions],
            "backups": [b.to_dict() for b in self.backups],
            "recoveries": [r.to_dict() for r in self.recoveries],
            "change_log": [c.to_dict() for c in self.change_log],
            "findings": [f.to_dict() for f in self.findings],
            "entry_count": self.entry_count,
            "issue_count": self.issue_count,
            "current_version": self.current_version,
            "synced": self.synced,
            "external_config_violations": self.external_config_violations,
            "protected_keys": self.protected_keys,
            "self_verification_passed": self.self_verification_passed,
            "readiness_status": self.readiness_status,
            "verdict": self.verdict,
            "cache_info": self.cache_info.to_dict(),
            "provenance": self.provenance.to_dict(),
            "metadata": dict(self.metadata),
            "is_empty": self.is_empty,
        }


__all__ = [
    "SOURCE_LOGGING", "SOURCE_MONITORING", "SOURCE_RESOURCE", "SOURCE_ENV",
    "SOURCE_WORKSPACE", "SOURCE_USER_REQUEST", "ALL_SOURCES",
    "SEVERITY_CRITICAL", "SEVERITY_HIGH", "SEVERITY_MEDIUM", "SEVERITY_LOW", "SEVERITY_INFO",
    "SCOPE_PLATFORM", "SCOPE_ENGINE", "SCOPE_WORKSPACE", "SCOPE_ENVIRONMENT", "ALL_SCOPES",
    "ISSUE_MISSING", "ISSUE_INVALID", "ISSUE_DUPLICATE", "ISSUE_UNSUPPORTED", "ALL_ISSUE_KINDS",
    "RULE_CENTRAL_ONLY", "RULE_VALIDATED", "RULE_VERSIONED", "RULE_PROTECTED",
    "RULE_SELF_VERIFICATION", "RULE_QUALITY_PASS", "ALL_QUALITY_RULES",
    "CACHE_HIT", "CACHE_MISS", "CACHE_DISABLED",
    "CONFIDENCE_HIGH", "CONFIDENCE_MEDIUM", "CONFIDENCE_LOW",
    "CONFIDENCE_HIGH_THRESHOLD", "CONFIDENCE_MEDIUM_THRESHOLD",
    "VERDICT_READY", "VERDICT_READY_WITH_WARNINGS", "VERDICT_NOT_READY", "ALL_VERDICTS",
    "SENSITIVE_KEYS",
    "ConfigEntry", "ValidationIssue", "ConfigVersion", "BackupRecord",
    "RecoveryRecord", "ConfigChangeLog", "ConfigFinding", "CacheInfo",
    "ConfigProvenance", "ConfigurationManagementReport",
]
