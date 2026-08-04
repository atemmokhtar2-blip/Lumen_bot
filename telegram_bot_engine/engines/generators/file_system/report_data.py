"""
File System Report (Specification 048 — CRITICAL).

Abstract file-system layer between all engines and the real FS.
No direct file access by other engines. Safe ops: validate → backup → verify → execute.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List


SOURCE_GIT_OPERATIONS = "git_operations_report"
SOURCE_REPOSITORY_MANAGEMENT = "repository_management_report"
SOURCE_PROJECT_CONTEXT = "project_context_report"
SOURCE_USER_REQUEST = "user_request"

ALL_SOURCES = (
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

# Operations
OP_CREATE_FILE = "create_file"
OP_DELETE_FILE = "delete_file"
OP_MOVE_FILE = "move_file"
OP_RENAME_FILE = "rename_file"
OP_COPY_FILE = "copy_file"
OP_READ_FILE = "read_file"
OP_WRITE_FILE = "write_file"
OP_APPEND_FILE = "append_file"
OP_REPLACE_FILE = "replace_file"
OP_CREATE_FOLDER = "create_folder"
OP_DELETE_FOLDER = "delete_folder"
OP_RENAME_FOLDER = "rename_folder"
OP_MOVE_FOLDER = "move_folder"

ALL_OPERATIONS = (
    OP_CREATE_FILE, OP_DELETE_FILE, OP_MOVE_FILE, OP_RENAME_FILE, OP_COPY_FILE,
    OP_READ_FILE, OP_WRITE_FILE, OP_APPEND_FILE, OP_REPLACE_FILE,
    OP_CREATE_FOLDER, OP_DELETE_FOLDER, OP_RENAME_FOLDER, OP_MOVE_FOLDER,
)

MUTATING_OPS = {
    OP_CREATE_FILE, OP_DELETE_FILE, OP_MOVE_FILE, OP_RENAME_FILE, OP_COPY_FILE,
    OP_WRITE_FILE, OP_APPEND_FILE, OP_REPLACE_FILE,
    OP_CREATE_FOLDER, OP_DELETE_FOLDER, OP_RENAME_FOLDER, OP_MOVE_FOLDER,
}

# Permissions
PERM_READ = "read"
PERM_WRITE = "write"
PERM_DELETE = "delete"
PERM_RENAME = "rename"
PERM_NONE = "none"

OP_REQUIRED_PERM = {
    OP_READ_FILE: PERM_READ,
    OP_CREATE_FILE: PERM_WRITE,
    OP_WRITE_FILE: PERM_WRITE,
    OP_APPEND_FILE: PERM_WRITE,
    OP_REPLACE_FILE: PERM_WRITE,
    OP_COPY_FILE: PERM_WRITE,
    OP_MOVE_FILE: PERM_WRITE,
    OP_RENAME_FILE: PERM_RENAME,
    OP_DELETE_FILE: PERM_DELETE,
    OP_CREATE_FOLDER: PERM_WRITE,
    OP_RENAME_FOLDER: PERM_RENAME,
    OP_MOVE_FOLDER: PERM_WRITE,
    OP_DELETE_FOLDER: PERM_DELETE,
}

RULE_PATH_VALID = "path_valid"
RULE_PERMISSION_OK = "permission_ok"
RULE_BACKUP_BEFORE_MUTATION = "backup_before_mutation"
RULE_INTEGRITY_OK = "integrity_ok"
RULE_WORKSPACE_ISOLATED = "workspace_isolated"
RULE_NO_DATA_LOSS = "no_data_loss"
RULE_SELF_VERIFICATION = "self_verification_passed"
RULE_QUALITY_PASS = "quality_pass"

ALL_QUALITY_RULES = (
    RULE_PATH_VALID,
    RULE_PERMISSION_OK,
    RULE_BACKUP_BEFORE_MUTATION,
    RULE_INTEGRITY_OK,
    RULE_WORKSPACE_ISOLATED,
    RULE_NO_DATA_LOSS,
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

STATUS_PLANNED = "planned"
STATUS_VALIDATED = "validated"
STATUS_BACKED_UP = "backed_up"
STATUS_EXECUTED = "executed"
STATUS_VERIFIED = "verified"
STATUS_DENIED = "denied"
STATUS_FAILED = "failed"
STATUS_RECOVERED = "recovered"


@dataclass
class PathCheck:
    check_id: str
    path: str
    valid: bool = True
    unsafe: bool = False
    issues: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "check_id": self.check_id,
            "path": self.path,
            "valid": self.valid,
            "unsafe": self.unsafe,
            "issues": list(self.issues),
        }


@dataclass
class PermissionCheck:
    check_id: str
    operation: str
    required: str = PERM_READ
    granted: str = PERM_NONE
    allowed: bool = False
    message: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "check_id": self.check_id,
            "operation": self.operation,
            "required": self.required,
            "granted": self.granted,
            "allowed": self.allowed,
            "message": self.message,
        }


@dataclass
class BackupRecord:
    backup_id: str
    original_path: str
    backup_path: str = ""
    timestamp: str = ""
    size_bytes: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "backup_id": self.backup_id,
            "original_path": self.original_path,
            "backup_path": self.backup_path,
            "timestamp": self.timestamp,
            "size_bytes": self.size_bytes,
        }


@dataclass
class IntegrityResult:
    path: str
    size_ok: bool = True
    encoding_ok: bool = True
    content_ok: bool = True
    intact: bool = True
    message: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "path": self.path,
            "size_ok": self.size_ok,
            "encoding_ok": self.encoding_ok,
            "content_ok": self.content_ok,
            "intact": self.intact,
            "message": self.message,
        }


@dataclass
class FileOperation:
    operation_id: str
    operation: str
    path: str = ""
    target_path: str = ""
    workspace_id: str = ""
    status: str = STATUS_PLANNED
    message: str = ""
    backup_id: str = ""
    integrity_ok: bool = False
    recovered: bool = False
    timestamp: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "operation_id": self.operation_id,
            "operation": self.operation,
            "path": self.path,
            "target_path": self.target_path,
            "workspace_id": self.workspace_id,
            "status": self.status,
            "message": self.message,
            "backup_id": self.backup_id,
            "integrity_ok": self.integrity_ok,
            "recovered": self.recovered,
            "timestamp": self.timestamp,
        }


@dataclass
class DuplicateInfo:
    duplicate_id: str
    paths: List[str] = field(default_factory=list)
    kind: str = "file"  # file|folder|resource

    def to_dict(self) -> Dict[str, Any]:
        return {
            "duplicate_id": self.duplicate_id,
            "paths": list(self.paths),
            "kind": self.kind,
        }


@dataclass
class FSFinding:
    severity: str
    code: str
    message: str
    affected: str = ""
    resolution_hint: str = ""
    category: str = "filesystem"

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
class FSProvenance:
    engine_name: str = "file_system"
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
class FileSystemReport:
    report_id: str = ""
    operations: List[FileOperation] = field(default_factory=list)
    path_checks: List[PathCheck] = field(default_factory=list)
    permission_checks: List[PermissionCheck] = field(default_factory=list)
    backups: List[BackupRecord] = field(default_factory=list)
    integrity: List[IntegrityResult] = field(default_factory=list)
    duplicates: List[DuplicateInfo] = field(default_factory=list)
    findings: List[FSFinding] = field(default_factory=list)
    operation_count: int = 0
    denied_count: int = 0
    failed_count: int = 0
    recovered_count: int = 0
    workspace_isolated: bool = True
    self_verification_passed: bool = False
    readiness_status: str = VERDICT_NOT_READY
    verdict: str = VERDICT_NOT_READY
    cache_info: CacheInfo = field(default_factory=CacheInfo)
    provenance: FSProvenance = field(default_factory=FSProvenance)
    metadata: Dict[str, Any] = field(default_factory=dict)
    is_empty: bool = True

    def to_dict(self) -> Dict[str, Any]:
        return {
            "report_id": self.report_id,
            "operations": [o.to_dict() for o in self.operations],
            "path_checks": [p.to_dict() for p in self.path_checks],
            "permission_checks": [p.to_dict() for p in self.permission_checks],
            "backups": [b.to_dict() for b in self.backups],
            "integrity": [i.to_dict() for i in self.integrity],
            "duplicates": [d.to_dict() for d in self.duplicates],
            "findings": [f.to_dict() for f in self.findings],
            "operation_count": self.operation_count,
            "denied_count": self.denied_count,
            "failed_count": self.failed_count,
            "recovered_count": self.recovered_count,
            "workspace_isolated": self.workspace_isolated,
            "self_verification_passed": self.self_verification_passed,
            "readiness_status": self.readiness_status,
            "verdict": self.verdict,
            "cache_info": self.cache_info.to_dict(),
            "provenance": self.provenance.to_dict(),
            "metadata": dict(self.metadata),
            "is_empty": self.is_empty,
        }


__all__ = [
    "SOURCE_GIT_OPERATIONS", "SOURCE_REPOSITORY_MANAGEMENT",
    "SOURCE_PROJECT_CONTEXT", "SOURCE_USER_REQUEST", "ALL_SOURCES",
    "SEVERITY_CRITICAL", "SEVERITY_HIGH", "SEVERITY_MEDIUM", "SEVERITY_LOW", "SEVERITY_INFO",
    "OP_CREATE_FILE", "OP_DELETE_FILE", "OP_MOVE_FILE", "OP_RENAME_FILE", "OP_COPY_FILE",
    "OP_READ_FILE", "OP_WRITE_FILE", "OP_APPEND_FILE", "OP_REPLACE_FILE",
    "OP_CREATE_FOLDER", "OP_DELETE_FOLDER", "OP_RENAME_FOLDER", "OP_MOVE_FOLDER",
    "ALL_OPERATIONS", "MUTATING_OPS", "OP_REQUIRED_PERM",
    "PERM_READ", "PERM_WRITE", "PERM_DELETE", "PERM_RENAME", "PERM_NONE",
    "RULE_PATH_VALID", "RULE_PERMISSION_OK", "RULE_BACKUP_BEFORE_MUTATION",
    "RULE_INTEGRITY_OK", "RULE_WORKSPACE_ISOLATED", "RULE_NO_DATA_LOSS",
    "RULE_SELF_VERIFICATION", "RULE_QUALITY_PASS", "ALL_QUALITY_RULES",
    "CACHE_HIT", "CACHE_MISS", "CACHE_DISABLED",
    "CONFIDENCE_HIGH", "CONFIDENCE_MEDIUM", "CONFIDENCE_LOW",
    "CONFIDENCE_HIGH_THRESHOLD", "CONFIDENCE_MEDIUM_THRESHOLD",
    "VERDICT_READY", "VERDICT_READY_WITH_WARNINGS", "VERDICT_NOT_READY", "VERDICT_DENIED",
    "ALL_VERDICTS",
    "STATUS_PLANNED", "STATUS_VALIDATED", "STATUS_BACKED_UP", "STATUS_EXECUTED",
    "STATUS_VERIFIED", "STATUS_DENIED", "STATUS_FAILED", "STATUS_RECOVERED",
    "PathCheck", "PermissionCheck", "BackupRecord", "IntegrityResult",
    "FileOperation", "DuplicateInfo", "FSFinding", "CacheInfo", "FSProvenance",
    "FileSystemReport",
]
