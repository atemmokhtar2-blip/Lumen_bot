"""
Security & Permission Management Report (Specification 060 — MAXIMUM CRITICAL).

Central permission registry, roles, least privilege, access validation,
engine isolation, sensitive resource protection, internal auth, audit
and security recovery.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List


SOURCE_CONFIG = "configuration_management_report"
SOURCE_LOGGING = "central_logging_report"
SOURCE_MONITORING = "system_monitoring_report"
SOURCE_EXECUTION_CONTEXT = "execution_context_report"
SOURCE_WORKSPACE = "workspace_management_report"
SOURCE_ECOSYSTEM = "engine_ecosystem_report"
SOURCE_USER_REQUEST = "user_request"

ALL_SOURCES = (
    SOURCE_CONFIG,
    SOURCE_LOGGING,
    SOURCE_MONITORING,
    SOURCE_EXECUTION_CONTEXT,
    SOURCE_WORKSPACE,
    SOURCE_ECOSYSTEM,
    SOURCE_USER_REQUEST,
)

SEVERITY_CRITICAL = "critical"
SEVERITY_HIGH = "high"
SEVERITY_MEDIUM = "medium"
SEVERITY_LOW = "low"
SEVERITY_INFO = "info"

# Permission kinds
PERM_READ = "read"
PERM_WRITE = "write"
PERM_EXECUTE = "execute"
PERM_ADMIN = "admin"
PERM_CONFIG = "config"
PERM_SECRET = "secret"
PERM_REPO = "repo"
PERM_WORKSPACE = "workspace"

ALL_PERMISSIONS = (
    PERM_READ, PERM_WRITE, PERM_EXECUTE, PERM_ADMIN,
    PERM_CONFIG, PERM_SECRET, PERM_REPO, PERM_WORKSPACE,
)

# Roles
ROLE_GENERATOR = "generator"
ROLE_ANALYZER = "analyzer"
ROLE_BUILDER = "builder"
ROLE_VALIDATOR = "validator"
ROLE_MONITOR = "monitor"
ROLE_LOGGER = "logger"
ROLE_CONFIG = "config"
ROLE_SECURITY = "security"
ROLE_ORCHESTRATOR = "orchestrator"
ROLE_SYSTEM = "system"

ALL_ROLES = (
    ROLE_GENERATOR, ROLE_ANALYZER, ROLE_BUILDER, ROLE_VALIDATOR,
    ROLE_MONITOR, ROLE_LOGGER, ROLE_CONFIG, ROLE_SECURITY,
    ROLE_ORCHESTRATOR, ROLE_SYSTEM,
)

# Default role → permissions (least privilege)
ROLE_PERMISSIONS: Dict[str, List[str]] = {
    ROLE_GENERATOR: [PERM_READ, PERM_WRITE, PERM_EXECUTE],
    ROLE_ANALYZER: [PERM_READ, PERM_EXECUTE],
    ROLE_BUILDER: [PERM_READ, PERM_WRITE, PERM_EXECUTE, PERM_WORKSPACE],
    ROLE_VALIDATOR: [PERM_READ, PERM_EXECUTE],
    ROLE_MONITOR: [PERM_READ, PERM_EXECUTE],
    ROLE_LOGGER: [PERM_READ, PERM_WRITE, PERM_EXECUTE],
    ROLE_CONFIG: [PERM_READ, PERM_WRITE, PERM_CONFIG, PERM_EXECUTE],
    ROLE_SECURITY: list(ALL_PERMISSIONS),  # security engine needs full view
    ROLE_ORCHESTRATOR: [PERM_READ, PERM_EXECUTE, PERM_ADMIN],
    ROLE_SYSTEM: list(ALL_PERMISSIONS),
}

RULE_LEAST_PRIVILEGE = "least_privilege_enforced"
RULE_NO_ROLE_CHANGE = "role_immutable_during_execution"
RULE_ACCESS_VALIDATED = "all_access_validated"
RULE_ISOLATION = "engine_isolation_enforced"
RULE_NO_UNAUTHORIZED = "no_unauthorized_access"
RULE_SELF_VERIFICATION = "self_verification_passed"
RULE_QUALITY_PASS = "quality_pass"

ALL_QUALITY_RULES = (
    RULE_LEAST_PRIVILEGE,
    RULE_NO_ROLE_CHANGE,
    RULE_ACCESS_VALIDATED,
    RULE_ISOLATION,
    RULE_NO_UNAUTHORIZED,
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

SENSITIVE_RESOURCES = (
    "secrets", "configurations", "tokens", "private_data", "repositories",
)


@dataclass
class PermissionGrant:
    engine_id: str
    permission: str
    resource: str = "*"
    granted: bool = True
    reason: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "engine_id": self.engine_id,
            "permission": self.permission,
            "resource": self.resource,
            "granted": self.granted,
            "reason": self.reason,
        }


@dataclass
class RoleAssignment:
    engine_id: str
    role: str
    locked: bool = True  # cannot change during execution
    permissions: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "engine_id": self.engine_id,
            "role": self.role,
            "locked": self.locked,
            "permissions": list(self.permissions),
        }


@dataclass
class AccessCheck:
    check_id: str
    engine_id: str
    permission: str
    resource: str = ""
    allowed: bool = False
    reason: str = ""
    ownership_ok: bool = True
    context_ok: bool = True

    def to_dict(self) -> Dict[str, Any]:
        return {
            "check_id": self.check_id,
            "engine_id": self.engine_id,
            "permission": self.permission,
            "resource": self.resource,
            "allowed": self.allowed,
            "reason": self.reason,
            "ownership_ok": self.ownership_ok,
            "context_ok": self.context_ok,
        }


@dataclass
class IsolationViolation:
    violation_id: str
    source_engine: str
    target_engine: str
    resource: str = ""
    message: str = ""
    blocked: bool = True

    def to_dict(self) -> Dict[str, Any]:
        return {
            "violation_id": self.violation_id,
            "source_engine": self.source_engine,
            "target_engine": self.target_engine,
            "resource": self.resource,
            "message": self.message,
            "blocked": self.blocked,
        }


@dataclass
class AuthRecord:
    engine_id: str
    identity: str
    authenticated: bool = False
    method: str = "internal"
    message: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "engine_id": self.engine_id,
            "identity": self.identity,
            "authenticated": self.authenticated,
            "method": self.method,
            "message": self.message,
        }


@dataclass
class SecurityAuditEntry:
    audit_id: str
    timestamp: str
    engine_id: str
    action: str
    result: str  # allowed | denied | recovered
    details: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "audit_id": self.audit_id,
            "timestamp": self.timestamp,
            "engine_id": self.engine_id,
            "action": self.action,
            "result": self.result,
            "details": self.details,
        }


@dataclass
class RecoveryAction:
    action_id: str
    timestamp: str
    engine_id: str
    action: str  # stop | isolate | report
    success: bool = True
    message: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "action_id": self.action_id,
            "timestamp": self.timestamp,
            "engine_id": self.engine_id,
            "action": self.action,
            "success": self.success,
            "message": self.message,
        }


@dataclass
class SecurityFinding:
    severity: str
    code: str
    message: str
    affected: str = ""
    resolution_hint: str = ""
    category: str = "security"

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
class SecurityProvenance:
    engine_name: str = "security_permission"
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
class SecurityPermissionReport:
    report_id: str = ""
    grants: List[PermissionGrant] = field(default_factory=list)
    roles: List[RoleAssignment] = field(default_factory=list)
    access_checks: List[AccessCheck] = field(default_factory=list)
    isolation_violations: List[IsolationViolation] = field(default_factory=list)
    auth_records: List[AuthRecord] = field(default_factory=list)
    audit_trail: List[SecurityAuditEntry] = field(default_factory=list)
    recoveries: List[RecoveryAction] = field(default_factory=list)
    findings: List[SecurityFinding] = field(default_factory=list)
    engine_count: int = 0
    denied_count: int = 0
    violation_count: int = 0
    unauthorized_attempts: int = 0
    recovered: bool = False
    self_verification_passed: bool = False
    readiness_status: str = VERDICT_NOT_READY
    verdict: str = VERDICT_NOT_READY
    cache_info: CacheInfo = field(default_factory=CacheInfo)
    provenance: SecurityProvenance = field(default_factory=SecurityProvenance)
    metadata: Dict[str, Any] = field(default_factory=dict)
    is_empty: bool = True

    def to_dict(self) -> Dict[str, Any]:
        return {
            "report_id": self.report_id,
            "grants": [g.to_dict() for g in self.grants],
            "roles": [r.to_dict() for r in self.roles],
            "access_checks": [a.to_dict() for a in self.access_checks],
            "isolation_violations": [v.to_dict() for v in self.isolation_violations],
            "auth_records": [a.to_dict() for a in self.auth_records],
            "audit_trail": [a.to_dict() for a in self.audit_trail],
            "recoveries": [r.to_dict() for r in self.recoveries],
            "findings": [f.to_dict() for f in self.findings],
            "engine_count": self.engine_count,
            "denied_count": self.denied_count,
            "violation_count": self.violation_count,
            "unauthorized_attempts": self.unauthorized_attempts,
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
    "SOURCE_CONFIG", "SOURCE_LOGGING", "SOURCE_MONITORING", "SOURCE_EXECUTION_CONTEXT",
    "SOURCE_WORKSPACE", "SOURCE_ECOSYSTEM", "SOURCE_USER_REQUEST", "ALL_SOURCES",
    "SEVERITY_CRITICAL", "SEVERITY_HIGH", "SEVERITY_MEDIUM", "SEVERITY_LOW", "SEVERITY_INFO",
    "PERM_READ", "PERM_WRITE", "PERM_EXECUTE", "PERM_ADMIN", "PERM_CONFIG",
    "PERM_SECRET", "PERM_REPO", "PERM_WORKSPACE", "ALL_PERMISSIONS",
    "ROLE_GENERATOR", "ROLE_ANALYZER", "ROLE_BUILDER", "ROLE_VALIDATOR",
    "ROLE_MONITOR", "ROLE_LOGGER", "ROLE_CONFIG", "ROLE_SECURITY",
    "ROLE_ORCHESTRATOR", "ROLE_SYSTEM", "ALL_ROLES", "ROLE_PERMISSIONS",
    "RULE_LEAST_PRIVILEGE", "RULE_NO_ROLE_CHANGE", "RULE_ACCESS_VALIDATED",
    "RULE_ISOLATION", "RULE_NO_UNAUTHORIZED", "RULE_SELF_VERIFICATION",
    "RULE_QUALITY_PASS", "ALL_QUALITY_RULES",
    "CACHE_HIT", "CACHE_MISS", "CACHE_DISABLED",
    "CONFIDENCE_HIGH", "CONFIDENCE_MEDIUM", "CONFIDENCE_LOW",
    "CONFIDENCE_HIGH_THRESHOLD", "CONFIDENCE_MEDIUM_THRESHOLD",
    "VERDICT_READY", "VERDICT_READY_WITH_WARNINGS", "VERDICT_NOT_READY", "ALL_VERDICTS",
    "SENSITIVE_RESOURCES",
    "PermissionGrant", "RoleAssignment", "AccessCheck", "IsolationViolation",
    "AuthRecord", "SecurityAuditEntry", "RecoveryAction", "SecurityFinding",
    "CacheInfo", "SecurityProvenance", "SecurityPermissionReport",
]
