"""Intelligent Git Operations Engine package (Specification 047)."""

from .git_operations_engine import GitOperationsEngine
from .report_data import (
    GitOperationsReport, GitOperation, CommitInfo, BranchInfo, ConflictInfo,
    HistoryEntry, GitFinding, CacheInfo, GitProvenance,
    ALL_SOURCES, ALL_QUALITY_RULES, ALL_VERDICTS, ALL_OPERATIONS, DANGEROUS_OPS,
    VERDICT_READY, VERDICT_READY_WITH_WARNINGS, VERDICT_NOT_READY, VERDICT_DENIED,
)

__all__ = [
    "smart_clone", "looks_like_clone_request", "extract_repo_url", "extract_token", "looks_like_git_token", "CloneResult",
    "GitOpResult", "detect_git_intent", "looks_like_git_request", "extract_repo_name",
    "create_github_repo", "git_push", "git_pull", "git_status", "run_git_intent",
    "GitEngineResult", "PowerGitEngine", "get_engine", "clone_multi_strategy",
    "atomic_commit", "create_ephemeral_branch", "rollback_hard",
    "structural_validate", "ensure_strict_gitignore",
    
    "GitOperationsEngine",
    "GitOperationsReport",
    "GitOperation",
    "CommitInfo",
    "BranchInfo",
    "ConflictInfo",
    "HistoryEntry",
    "GitFinding",
    "CacheInfo",
    "GitProvenance",
    "ALL_SOURCES",
    "ALL_QUALITY_RULES",
    "ALL_VERDICTS",
    "ALL_OPERATIONS",
    "DANGEROUS_OPS",
    "VERDICT_READY",
    "VERDICT_READY_WITH_WARNINGS",
    "VERDICT_NOT_READY",
    "VERDICT_DENIED",
]

from .smart_clone import smart_clone, looks_like_clone_request, extract_repo_url, extract_token, looks_like_git_token, CloneResult
from .smart_git import (
    GitOpResult,
    detect_git_intent,
    looks_like_git_request,
    extract_repo_name,
    create_github_repo,
    git_push,
    git_pull,
    git_status,
    run_git_intent,
)

# Power Git Engine (performance / security / honest verify / safe workflow)
from .power import (
    GitEngineResult,
    PowerGitEngine,
    get_engine,
    clone_multi_strategy,
    atomic_commit,
    create_ephemeral_branch,
    rollback_hard,
    structural_validate,
    ensure_strict_gitignore,
)
