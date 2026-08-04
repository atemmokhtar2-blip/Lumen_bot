"""Intelligent Git Operations Engine package (Specification 047)."""

from .git_operations_engine import GitOperationsEngine
from .report_data import (
    GitOperationsReport, GitOperation, CommitInfo, BranchInfo, ConflictInfo,
    HistoryEntry, GitFinding, CacheInfo, GitProvenance,
    ALL_SOURCES, ALL_QUALITY_RULES, ALL_VERDICTS, ALL_OPERATIONS, DANGEROUS_OPS,
    VERDICT_READY, VERDICT_READY_WITH_WARNINGS, VERDICT_NOT_READY, VERDICT_DENIED,
)

__all__ = [
    "smart_clone", "looks_like_clone_request", "extract_repo_url", "CloneResult",
    
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

from .smart_clone import smart_clone, looks_like_clone_request, extract_repo_url, CloneResult
