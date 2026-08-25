"""
Workspace Management Report (Specification 049 — CRITICAL).

Manages isolated project workspaces: create/open/suspend/resume/archive/delete.
No cross-workspace access. No data loss. Snapshots + recovery + cleanup.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List


SOURCE_FILE_SYSTEM = "file_system_report"
SOURCE_GIT_OPERATIONS = "git_operations_report"
SOURCE_REPOSITORY_MANAGEMENT = "repository_management_report"
SOURCE_PROJECT_CONTEXT = "project_context_report"
SOURCE_USER_REQUEST = "user_request"

ALL_SOURCES = (
    SOURCE_FILE_SYSTEM,
    SOURCE_GIT_OPERATIONS,
    SOURCE_REPOSITORY_MANAGEMENT,
    SOURCE_PROJECT_CONTEXT,
    SOURCE_USER_REQUEST,
)

SEVERITY_CRITICAL = "critical"
SEVERITY_HIGH = "high"
SEVERITY_MEDIUM = "medium"
SEVERITY_LOW = "low"
SEVERITY_INFO = "info"

# Lifecycle actions
ACT_CREATE = "create"
ACT_OPEN = "open"
ACT_SUSPEND = "suspend"
ACT_RESUME = "resume"
ACT_ARCHIVE = "archive"
ACT_DELETE = "delete"
ACT_SNAPSHOT = "snapshot"
ACT_CLEANUP = "cleanup"
ACT_VALIDATE = "validate"
ACT_MONITOR = "monitor"
ACT_RECOVER = "recover"

ALL_ACTIONS = (
    ACT_CREATE, ACT_OPEN, ACT_SUSPEND, ACT_RESUME, ACT_ARCHIVE, ACT_DELETE,
    ACT_SNAPSHOT, ACT_CLEANUP, ACT_VALIDATE, ACT_MONITOR, ACT_RECOVER,
)

# Workspace status
WS_ACTIVE = "active"
WS_SUSPENDED = "suspended"
WS_ARCHIVED = "archived"
WS_DELETED = "deleted"
WS_TEMPORARY = "temporary"
WS_RECOVERING = "recovering"

ALL_WS_STATUS = (WS_ACTIVE, WS_SUSPENDED, WS_ARCHIVED, WS_DELETED, WS_TEMPORARY, WS_RECOVERING)

RULE_NO_CROSS_ACCESS = "no_cross_workspace_access"
RULE_ISOLATION_OK = "isolation_ok"
RULE_NO_DATA_LOSS = "no_data_loss"
RULE_LIFECYCLE_VALID = "lifecycle_valid"
RULE_SELF_VERIFICATION = "self_verification_passed"
RULE_QUALITY_PASS = "quality_pass"

ALL_QUALITY_RULES = (
    RULE_NO_CROSS_ACCESS,
    RULE_ISOLATION_OK,
    RULE_NO_DATA_LOSS,
    RULE_LIFECYCLE_VALID,
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
VERDICT_DENIED = "denied"

ALL_VERDICTS = (
    VERDICT_READY, VERDICT_READY_WITH_WARNINGS, VERDICT_NOT_READY, VERDICT_DENIED,
)

STATUS_OK = "ok"
STATUS_FAILED = "failed"
STATUS_DENIED = "denied"
STATUS_RECOVERED = "recovered"


@dataclass
class WorkspaceRecord:
    workspace_id: str
    owner: str = ""
    project_type: str = "telegram_bot"
    status: str = WS_ACTIVE
    created_at: str = ""
    is_temporary: bool = False
    path: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "workspace_id": self.workspace_id,
            "owner": self.owner,
            "project_type": self.project_type,
            "status": self.status,
            "created_at": self.created_at,
            "is_temporary": self.is_temporary,
            "path": self.path,
        }


@dataclass
class ResourceUsage:
    workspace_id: str
    cpu_percent: float = 0.0
    ram_mb: float = 0.0
    storage_mb: float = 0.0
    file_count: int = 0
    folder_count: int = 0
    temp_files: int = 0
    log_files: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "workspace_id": self.workspace_id,
            "cpu_percent": self.cpu_percent,
            "ram_mb": self.ram_mb,
            "storage_mb": self.storage_mb,
            "file_count": self.file_count,
            "folder_count": self.folder_count,
            "temp_files": self.temp_files,
            "log_files": self.log_files,
        }


@dataclass
class SnapshotRecord:
    snapshot_id: str
    workspace_id: str
    created_at: str = ""
    label: str = ""
    size_mb: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "snapshot_id": self.snapshot_id,
            "workspace_id": self.workspace_id,
            "created_at": self.created_at,
            "label": self.label,
            "size_mb": self.size_mb,
        }


@dataclass
class WorkspaceAction:
    action_id: str
    action: str
    workspace_id: str
    status: str = STATUS_OK
    message: str = ""
    timestamp: str = ""
    actor: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "action_id": self.action_id,
            "action": self.action,
            "workspace_id": self.workspace_id,
            "status": self.status,
            "message": self.message,
            "timestamp": self.timestamp,
            "actor": self.actor,
        }


@dataclass
class ValidationResult:
    workspace_id: str
    integrity_ok: bool = True
    consistency_ok: bool = True
    permissions_ok: bool = True
    structure_ok: bool = True
    overall_ok: bool = True
    message: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "workspace_id": self.workspace_id,
            "integrity_ok": self.integrity_ok,
            "consistency_ok": self.consistency_ok,
            "permissions_ok": self.permissions_ok,
            "structure_ok": self.structure_ok,
            "overall_ok": self.overall_ok,
            "message": self.message,
        }


@dataclass
class WorkspaceFinding:
    severity: str
    code: str
    message: str
    affected: str = ""
    resolution_hint: str = ""
    category: str = "workspace"

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
class WorkspaceProvenance:
    engine_name: str = "workspace_management"
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
class WorkspaceManagementReport:
    report_id: str = ""
    workspaces: List[WorkspaceRecord] = field(default_factory=list)
    actions: List[WorkspaceAction] = field(default_factory=list)
    resources: List[ResourceUsage] = field(default_factory=list)
    snapshots: List[SnapshotRecord] = field(default_factory=list)
    validations: List[ValidationResult] = field(default_factory=list)
    findings: List[WorkspaceFinding] = field(default_factory=list)
    workspace_count: int = 0
    action_count: int = 0
    failed_count: int = 0
    isolation_ok: bool = True
    self_verification_passed: bool = False
    readiness_status: str = VERDICT_NOT_READY
    verdict: str = VERDICT_NOT_READY
    cache_info: CacheInfo = field(default_factory=CacheInfo)
    provenance: WorkspaceProvenance = field(default_factory=WorkspaceProvenance)
    metadata: Dict[str, Any] = field(default_factory=dict)
    is_empty: bool = True

    def to_dict(self) -> Dict[str, Any]:
        return {
            "report_id": self.report_id,
            "workspaces": [w.to_dict() for w in self.workspaces],
            "actions": [a.to_dict() for a in self.actions],
            "resources": [r.to_dict() for r in self.resources],
            "snapshots": [s.to_dict() for s in self.snapshots],
            "validations": [v.to_dict() for v in self.validations],
            "findings": [f.to_dict() for f in self.findings],
            "workspace_count": self.workspace_count,
            "action_count": self.action_count,
            "failed_count": self.failed_count,
            "isolation_ok": self.isolation_ok,
            "self_verification_passed": self.self_verification_passed,
            "readiness_status": self.readiness_status,
            "verdict": self.verdict,
            "cache_info": self.cache_info.to_dict(),
            "provenance": self.provenance.to_dict(),
            "metadata": dict(self.metadata),
            "is_empty": self.is_empty,
        }


__all__ = [
    "SOURCE_FILE_SYSTEM", "SOURCE_GIT_OPERATIONS", "SOURCE_REPOSITORY_MANAGEMENT",
    "SOURCE_PROJECT_CONTEXT", "SOURCE_USER_REQUEST", "ALL_SOURCES",
    "SEVERITY_CRITICAL", "SEVERITY_HIGH", "SEVERITY_MEDIUM", "SEVERITY_LOW", "SEVERITY_INFO",
    "ACT_CREATE", "ACT_OPEN", "ACT_SUSPEND", "ACT_RESUME", "ACT_ARCHIVE", "ACT_DELETE",
    "ACT_SNAPSHOT", "ACT_CLEANUP", "ACT_VALIDATE", "ACT_MONITOR", "ACT_RECOVER",
    "ALL_ACTIONS",
    "WS_ACTIVE", "WS_SUSPENDED", "WS_ARCHIVED", "WS_DELETED", "WS_TEMPORARY", "WS_RECOVERING",
    "ALL_WS_STATUS",
    "RULE_NO_CROSS_ACCESS", "RULE_ISOLATION_OK", "RULE_NO_DATA_LOSS",
    "RULE_LIFECYCLE_VALID", "RULE_SELF_VERIFICATION", "RULE_QUALITY_PASS",
    "ALL_QUALITY_RULES",
    "CACHE_HIT", "CACHE_MISS", "CACHE_DISABLED",
    "CONFIDENCE_HIGH", "CONFIDENCE_MEDIUM", "CONFIDENCE_LOW",
    "CONFIDENCE_HIGH_THRESHOLD", "CONFIDENCE_MEDIUM_THRESHOLD",
    "VERDICT_READY", "VERDICT_READY_WITH_WARNINGS", "VERDICT_NOT_READY", "VERDICT_DENIED",
    "ALL_VERDICTS",
    "STATUS_OK", "STATUS_FAILED", "STATUS_DENIED", "STATUS_RECOVERED",
    "WorkspaceRecord", "ResourceUsage", "SnapshotRecord", "WorkspaceAction",
    "ValidationResult", "WorkspaceFinding", "CacheInfo", "WorkspaceProvenance",
    "WorkspaceManagementReport",
]
