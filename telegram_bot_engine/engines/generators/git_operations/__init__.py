"""Intelligent Git Operations Engine package (Specification 047)."""

from .git_operations_engine import GitOperationsEngine
from .report_data import (
    GitOperationsReport, GitOperation, CommitInfo, BranchInfo, ConflictInfo,
    HistoryEntry, GitFinding, CacheInfo, GitProvenance,
    ALL_SOURCES, ALL_QUALITY_RULES, ALL_VERDICTS, ALL_OPERATIONS, DANGEROUS_OPS,
    VERDICT_READY, VERDICT_READY_WITH_WARNINGS, VERDICT_NOT_READY, VERDICT_DENIED,
)

__all__ = [
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
