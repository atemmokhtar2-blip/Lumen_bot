"""Intelligent Repository Management Engine package (Specification 046)."""

from .repository_management_engine import RepositoryManagementEngine
from .report_data import (
    RepositoryManagementReport, PermissionCheck, OperationPlan, OperationResult,
    RepoDiscovery, RepoFinding, CacheInfo, RepoProvenance,
    ALL_SOURCES, ALL_QUALITY_RULES, ALL_VERDICTS, ALL_OPERATIONS,
    VERDICT_READY, VERDICT_READY_WITH_WARNINGS, VERDICT_NOT_READY, VERDICT_DENIED,
)

__all__ = [
    "RepositoryManagementEngine",
    "RepositoryManagementReport",
    "PermissionCheck",
    "OperationPlan",
    "OperationResult",
    "RepoDiscovery",
    "RepoFinding",
    "CacheInfo",
    "RepoProvenance",
    "ALL_SOURCES",
    "ALL_QUALITY_RULES",
    "ALL_VERDICTS",
    "ALL_OPERATIONS",
    "VERDICT_READY",
    "VERDICT_READY_WITH_WARNINGS",
    "VERDICT_NOT_READY",
    "VERDICT_DENIED",
]
