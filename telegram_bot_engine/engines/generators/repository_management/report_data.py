"""
Repository Management Report (Specification 046 — CRITICAL).

Manages user repositories only after ownership and permission verification.
Never acts autonomously — only executes explicit user requests.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List


SOURCE_PROJECT_CONTEXT = "project_context_report"
SOURCE_PRODUCTION_READINESS = "production_readiness_report"
SOURCE_USER_REQUEST = "user_request"

ALL_SOURCES = (
    SOURCE_PROJECT_CONTEXT,
    SOURCE_PRODUCTION_READINESS,
    SOURCE_USER_REQUEST,
)

SEVERITY_CRITICAL = "critical"
SEVERITY_HIGH = "high"
SEVERITY_MEDIUM = "medium"
SEVERITY_LOW = "low"
SEVERITY_INFO = "info"

# Operations
OP_CLONE = "clone"
OP_FETCH = "fetch"
OP_PULL = "pull"
OP_COMMIT = "commit"
OP_PUSH = "push"
OP_CREATE_BRANCH = "create_branch"
OP_DELETE_BRANCH = "delete_branch"
OP_MERGE_BRANCH = "merge_branch"
OP_CREATE_REPO = "create_repository"
OP_RENAME_REPO = "rename_repository"
OP_ARCHIVE_REPO = "archive_repository"
OP_DISCOVER = "discover"
OP_LIST_BRANCHES = "list_branches"
OP_LIST_TAGS = "list_tags"
OP_LIST_COMMITS = "list_commits"
OP_LIST_RELEASES = "list_releases"

ALL_OPERATIONS = (
    OP_CLONE, OP_FETCH, OP_PULL, OP_COMMIT, OP_PUSH,
    OP_CREATE_BRANCH, OP_DELETE_BRANCH, OP_MERGE_BRANCH,
    OP_CREATE_REPO, OP_RENAME_REPO, OP_ARCHIVE_REPO,
    OP_DISCOVER, OP_LIST_BRANCHES, OP_LIST_TAGS,
    OP_LIST_COMMITS, OP_LIST_RELEASES,
)

# Permission levels
PERM_READ = "read"
PERM_WRITE = "write"
PERM_ADMIN = "admin"
PERM_NONE = "none"

# Required permission per operation
OP_REQUIRED_PERM = {
    OP_CLONE: PERM_READ,
    OP_FETCH: PERM_READ,
    OP_PULL: PERM_READ,
    OP_DISCOVER: PERM_READ,
    OP_LIST_BRANCHES: PERM_READ,
    OP_LIST_TAGS: PERM_READ,
    OP_LIST_COMMITS: PERM_READ,
    OP_LIST_RELEASES: PERM_READ,
    OP_COMMIT: PERM_WRITE,
    OP_PUSH: PERM_WRITE,
    OP_CREATE_BRANCH: PERM_WRITE,
    OP_DELETE_BRANCH: PERM_WRITE,
    OP_MERGE_BRANCH: PERM_WRITE,
    OP_CREATE_REPO: PERM_ADMIN,
    OP_RENAME_REPO: PERM_ADMIN,
    OP_ARCHIVE_REPO: PERM_ADMIN,
}

RULE_OWNERSHIP_VERIFIED = "ownership_verified"
RULE_PERMISSION_SUFFICIENT = "permission_sufficient"
RULE_NO_AUTONOMOUS_ACTION = "no_autonomous_action"
RULE_PLAN_BEFORE_MUTATION = "plan_before_mutation"
RULE_SELF_VERIFICATION = "self_verification_passed"
RULE_QUALITY_PASS = "quality_pass"

ALL_QUALITY_RULES = (
    RULE_OWNERSHIP_VERIFIED,
    RULE_PERMISSION_SUFFICIENT,
    RULE_NO_AUTONOMOUS_ACTION,
    RULE_PLAN_BEFORE_MUTATION,
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
STATUS_EXECUTED = "executed"
STATUS_DENIED = "denied"
STATUS_FAILED = "failed"
STATUS_SKIPPED = "skipped"
STATUS_RECOVERED = "recovered"


@dataclass
class PermissionCheck:
    check_id: str
    operation: str
    required: str = PERM_READ
    granted: str = PERM_NONE
    ownership_verified: bool = False
    allowed: bool = False
    message: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "check_id": self.check_id,
            "operation": self.operation,
            "required": self.required,
            "granted": self.granted,
            "ownership_verified": self.ownership_verified,
            "allowed": self.allowed,
            "message": self.message,
        }


@dataclass
class OperationPlan:
    plan_id: str
    operation: str
    repository: str = ""
    branch: str = ""
    details: str = ""
    mutating: bool = False
    status: str = STATUS_PLANNED

    def to_dict(self) -> Dict[str, Any]:
        return {
            "plan_id": self.plan_id,
            "operation": self.operation,
            "repository": self.repository,
            "branch": self.branch,
            "details": self.details,
            "mutating": self.mutating,
            "status": self.status,
        }


@dataclass
class OperationResult:
    result_id: str
    operation: str
    plan_id: str = ""
    status: str = STATUS_EXECUTED
    message: str = ""
    repository: str = ""
    user_id: str = ""
    timestamp: str = ""
    conflict: str = ""
    recovered: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "result_id": self.result_id,
            "operation": self.operation,
            "plan_id": self.plan_id,
            "status": self.status,
            "message": self.message,
            "repository": self.repository,
            "user_id": self.user_id,
            "timestamp": self.timestamp,
            "conflict": self.conflict,
            "recovered": self.recovered,
        }


@dataclass
class RepoDiscovery:
    discovery_id: str
    repository: str = ""
    branches: List[str] = field(default_factory=list)
    tags: List[str] = field(default_factory=list)
    commits: List[str] = field(default_factory=list)
    releases: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "discovery_id": self.discovery_id,
            "repository": self.repository,
            "branches": list(self.branches),
            "tags": list(self.tags),
            "commits": list(self.commits),
            "releases": list(self.releases),
        }


@dataclass
class RepoFinding:
    severity: str
    code: str
    message: str
    affected: str = ""
    resolution_hint: str = ""
    category: str = "repository"

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
class RepoProvenance:
    engine_name: str = "repository_management"
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
class RepositoryManagementReport:
    report_id: str = ""
    permission_checks: List[PermissionCheck] = field(default_factory=list)
    plans: List[OperationPlan] = field(default_factory=list)
    results: List[OperationResult] = field(default_factory=list)
    discoveries: List[RepoDiscovery] = field(default_factory=list)
    findings: List[RepoFinding] = field(default_factory=list)
    operation_count: int = 0
    denied_count: int = 0
    failed_count: int = 0
    ownership_verified: bool = False
    self_verification_passed: bool = False
    readiness_status: str = VERDICT_NOT_READY
    verdict: str = VERDICT_NOT_READY
    cache_info: CacheInfo = field(default_factory=CacheInfo)
    provenance: RepoProvenance = field(default_factory=RepoProvenance)
    metadata: Dict[str, Any] = field(default_factory=dict)
    is_empty: bool = True

    def to_dict(self) -> Dict[str, Any]:
        return {
            "report_id": self.report_id,
            "permission_checks": [p.to_dict() for p in self.permission_checks],
            "plans": [p.to_dict() for p in self.plans],
            "results": [r.to_dict() for r in self.results],
            "discoveries": [d.to_dict() for d in self.discoveries],
            "findings": [f.to_dict() for f in self.findings],
            "operation_count": self.operation_count,
            "denied_count": self.denied_count,
            "failed_count": self.failed_count,
            "ownership_verified": self.ownership_verified,
            "self_verification_passed": self.self_verification_passed,
            "readiness_status": self.readiness_status,
            "verdict": self.verdict,
            "cache_info": self.cache_info.to_dict(),
            "provenance": self.provenance.to_dict(),
            "metadata": dict(self.metadata),
            "is_empty": self.is_empty,
        }


__all__ = [
    "SOURCE_PROJECT_CONTEXT", "SOURCE_PRODUCTION_READINESS", "SOURCE_USER_REQUEST",
    "ALL_SOURCES",
    "SEVERITY_CRITICAL", "SEVERITY_HIGH", "SEVERITY_MEDIUM", "SEVERITY_LOW", "SEVERITY_INFO",
    "OP_CLONE", "OP_FETCH", "OP_PULL", "OP_COMMIT", "OP_PUSH",
    "OP_CREATE_BRANCH", "OP_DELETE_BRANCH", "OP_MERGE_BRANCH",
    "OP_CREATE_REPO", "OP_RENAME_REPO", "OP_ARCHIVE_REPO",
    "OP_DISCOVER", "OP_LIST_BRANCHES", "OP_LIST_TAGS", "OP_LIST_COMMITS", "OP_LIST_RELEASES",
    "ALL_OPERATIONS", "OP_REQUIRED_PERM",
    "PERM_READ", "PERM_WRITE", "PERM_ADMIN", "PERM_NONE",
    "RULE_OWNERSHIP_VERIFIED", "RULE_PERMISSION_SUFFICIENT", "RULE_NO_AUTONOMOUS_ACTION",
    "RULE_PLAN_BEFORE_MUTATION", "RULE_SELF_VERIFICATION", "RULE_QUALITY_PASS",
    "ALL_QUALITY_RULES",
    "CACHE_HIT", "CACHE_MISS", "CACHE_DISABLED",
    "CONFIDENCE_HIGH", "CONFIDENCE_MEDIUM", "CONFIDENCE_LOW",
    "CONFIDENCE_HIGH_THRESHOLD", "CONFIDENCE_MEDIUM_THRESHOLD",
    "VERDICT_READY", "VERDICT_READY_WITH_WARNINGS", "VERDICT_NOT_READY", "VERDICT_DENIED",
    "ALL_VERDICTS",
    "STATUS_PLANNED", "STATUS_EXECUTED", "STATUS_DENIED", "STATUS_FAILED",
    "STATUS_SKIPPED", "STATUS_RECOVERED",
    "PermissionCheck", "OperationPlan", "OperationResult", "RepoDiscovery",
    "RepoFinding", "CacheInfo", "RepoProvenance", "RepositoryManagementReport",
]
