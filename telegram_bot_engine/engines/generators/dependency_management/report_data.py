"""
Dependency & Package Management Report (Specification 050 — ULTRA CRITICAL).

Discovers, validates, resolves and locks project dependencies.
Blocks incompatible, unsafe or unused packages. Health scoring + offline registry.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List


SOURCE_WORKSPACE = "workspace_management_report"
SOURCE_FILE_SYSTEM = "file_system_report"
SOURCE_PROJECT_CONTEXT = "project_context_report"
SOURCE_ARCHITECTURE = "architecture_compliance_report"
SOURCE_USER_REQUEST = "user_request"

ALL_SOURCES = (
    SOURCE_WORKSPACE,
    SOURCE_FILE_SYSTEM,
    SOURCE_PROJECT_CONTEXT,
    SOURCE_ARCHITECTURE,
    SOURCE_USER_REQUEST,
)

SEVERITY_CRITICAL = "critical"
SEVERITY_HIGH = "high"
SEVERITY_MEDIUM = "medium"
SEVERITY_LOW = "low"
SEVERITY_INFO = "info"

# Dependency kinds
KIND_PACKAGE = "package"
KIND_LIBRARY = "library"
KIND_FRAMEWORK = "framework"
KIND_PLUGIN = "plugin"
KIND_EXTENSION = "extension"

# Conflict types
CONFLICT_VERSION = "version_conflict"
CONFLICT_PACKAGE = "package_conflict"
CONFLICT_CIRCULAR = "circular_dependency"
CONFLICT_BROKEN = "broken_dependency"

# Security flags
SEC_DEPRECATED = "deprecated"
SEC_UNSAFE = "unsafe"
SEC_VULNERABLE = "known_vulnerability"
SEC_OK = "ok"

RULE_NO_INCOMPATIBLE = "no_incompatible_dependency"
RULE_NO_UNSAFE = "no_unsafe_dependency"
RULE_NO_UNUSED = "no_unused_dependency"
RULE_CONFLICTS_RESOLVED = "conflicts_resolved"
RULE_LOCKFILE_PRESENT = "lockfile_present"
RULE_SELF_VERIFICATION = "self_verification_passed"
RULE_QUALITY_PASS = "quality_pass"

ALL_QUALITY_RULES = (
    RULE_NO_INCOMPATIBLE,
    RULE_NO_UNSAFE,
    RULE_NO_UNUSED,
    RULE_CONFLICTS_RESOLVED,
    RULE_LOCKFILE_PRESENT,
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
STATUS_CONFLICT = "conflict"
STATUS_UNSAFE = "unsafe"
STATUS_UNUSED = "unused"
STATUS_RESOLVED = "resolved"
STATUS_BLOCKED = "blocked"


@dataclass
class Dependency:
    dep_id: str
    name: str
    version: str = ""
    kind: str = KIND_PACKAGE
    required: bool = True
    used: bool = True
    compatible: bool = True
    security: str = SEC_OK
    source: str = ""  # e.g. requirements.txt / package.json
    pinned: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "dep_id": self.dep_id,
            "name": self.name,
            "version": self.version,
            "kind": self.kind,
            "required": self.required,
            "used": self.used,
            "compatible": self.compatible,
            "security": self.security,
            "source": self.source,
            "pinned": self.pinned,
        }


@dataclass
class Conflict:
    conflict_id: str
    conflict_type: str
    packages: List[str] = field(default_factory=list)
    message: str = ""
    suggestion: str = ""
    resolved: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "conflict_id": self.conflict_id,
            "conflict_type": self.conflict_type,
            "packages": list(self.packages),
            "message": self.message,
            "suggestion": self.suggestion,
            "resolved": self.resolved,
        }


@dataclass
class SecurityIssue:
    issue_id: str
    package: str
    version: str = ""
    flag: str = SEC_VULNERABLE
    severity: str = SEVERITY_HIGH
    message: str = ""
    advisory: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "issue_id": self.issue_id,
            "package": self.package,
            "version": self.version,
            "flag": self.flag,
            "severity": self.severity,
            "message": self.message,
            "advisory": self.advisory,
        }


@dataclass
class HealthScore:
    compatibility: float = 0.0
    security: float = 0.0
    stability: float = 0.0
    maintainability: float = 0.0
    overall: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "compatibility": self.compatibility,
            "security": self.security,
            "stability": self.stability,
            "maintainability": self.maintainability,
            "overall": self.overall,
        }


@dataclass
class LockEntry:
    name: str
    version: str
    hash: str = ""
    source: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "version": self.version,
            "hash": self.hash,
            "source": self.source,
        }


@dataclass
class RegistryEntry:
    name: str
    version: str
    verified_at: str = ""
    stable: bool = True

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "version": self.version,
            "verified_at": self.verified_at,
            "stable": self.stable,
        }


@dataclass
class DepFinding:
    severity: str
    code: str
    message: str
    affected: str = ""
    resolution_hint: str = ""
    category: str = "dependency"

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
class DepProvenance:
    engine_name: str = "dependency_management"
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
class DependencyManagementReport:
    report_id: str = ""
    dependencies: List[Dependency] = field(default_factory=list)
    conflicts: List[Conflict] = field(default_factory=list)
    security_issues: List[SecurityIssue] = field(default_factory=list)
    unused: List[str] = field(default_factory=list)
    lockfile: List[LockEntry] = field(default_factory=list)
    registry: List[RegistryEntry] = field(default_factory=list)
    health: HealthScore = field(default_factory=HealthScore)
    findings: List[DepFinding] = field(default_factory=list)
    dependency_count: int = 0
    conflict_count: int = 0
    unsafe_count: int = 0
    unused_count: int = 0
    self_verification_passed: bool = False
    readiness_status: str = VERDICT_NOT_READY
    verdict: str = VERDICT_NOT_READY
    cache_info: CacheInfo = field(default_factory=CacheInfo)
    provenance: DepProvenance = field(default_factory=DepProvenance)
    metadata: Dict[str, Any] = field(default_factory=dict)
    is_empty: bool = True

    def to_dict(self) -> Dict[str, Any]:
        return {
            "report_id": self.report_id,
            "dependencies": [d.to_dict() for d in self.dependencies],
            "conflicts": [c.to_dict() for c in self.conflicts],
            "security_issues": [s.to_dict() for s in self.security_issues],
            "unused": list(self.unused),
            "lockfile": [l.to_dict() for l in self.lockfile],
            "registry": [r.to_dict() for r in self.registry],
            "health": self.health.to_dict(),
            "findings": [f.to_dict() for f in self.findings],
            "dependency_count": self.dependency_count,
            "conflict_count": self.conflict_count,
            "unsafe_count": self.unsafe_count,
            "unused_count": self.unused_count,
            "self_verification_passed": self.self_verification_passed,
            "readiness_status": self.readiness_status,
            "verdict": self.verdict,
            "cache_info": self.cache_info.to_dict(),
            "provenance": self.provenance.to_dict(),
            "metadata": dict(self.metadata),
            "is_empty": self.is_empty,
        }


__all__ = [
    "SOURCE_WORKSPACE", "SOURCE_FILE_SYSTEM", "SOURCE_PROJECT_CONTEXT",
    "SOURCE_ARCHITECTURE", "SOURCE_USER_REQUEST", "ALL_SOURCES",
    "SEVERITY_CRITICAL", "SEVERITY_HIGH", "SEVERITY_MEDIUM", "SEVERITY_LOW", "SEVERITY_INFO",
    "KIND_PACKAGE", "KIND_LIBRARY", "KIND_FRAMEWORK", "KIND_PLUGIN", "KIND_EXTENSION",
    "CONFLICT_VERSION", "CONFLICT_PACKAGE", "CONFLICT_CIRCULAR", "CONFLICT_BROKEN",
    "SEC_DEPRECATED", "SEC_UNSAFE", "SEC_VULNERABLE", "SEC_OK",
    "RULE_NO_INCOMPATIBLE", "RULE_NO_UNSAFE", "RULE_NO_UNUSED",
    "RULE_CONFLICTS_RESOLVED", "RULE_LOCKFILE_PRESENT",
    "RULE_SELF_VERIFICATION", "RULE_QUALITY_PASS", "ALL_QUALITY_RULES",
    "CACHE_HIT", "CACHE_MISS", "CACHE_DISABLED",
    "CONFIDENCE_HIGH", "CONFIDENCE_MEDIUM", "CONFIDENCE_LOW",
    "CONFIDENCE_HIGH_THRESHOLD", "CONFIDENCE_MEDIUM_THRESHOLD",
    "VERDICT_READY", "VERDICT_READY_WITH_WARNINGS", "VERDICT_NOT_READY", "ALL_VERDICTS",
    "STATUS_OK", "STATUS_CONFLICT", "STATUS_UNSAFE", "STATUS_UNUSED",
    "STATUS_RESOLVED", "STATUS_BLOCKED",
    "Dependency", "Conflict", "SecurityIssue", "HealthScore", "LockEntry",
    "RegistryEntry", "DepFinding", "CacheInfo", "DepProvenance",
    "DependencyManagementReport",
]
