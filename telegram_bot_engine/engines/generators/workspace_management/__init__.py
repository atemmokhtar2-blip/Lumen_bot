"""Intelligent Workspace Management Engine package (Specification 049)."""

from .workspace_management_engine import WorkspaceManagementEngine
from .report_data import (
    WorkspaceManagementReport, WorkspaceRecord, WorkspaceAction, ResourceUsage,
    SnapshotRecord, ValidationResult, WorkspaceFinding, CacheInfo, WorkspaceProvenance,
    ALL_SOURCES, ALL_QUALITY_RULES, ALL_VERDICTS, ALL_ACTIONS,
    VERDICT_READY, VERDICT_READY_WITH_WARNINGS, VERDICT_NOT_READY, VERDICT_DENIED,
)

__all__ = [
    "WorkspaceManagementEngine",
    "WorkspaceManagementReport",
    "WorkspaceRecord",
    "WorkspaceAction",
    "ResourceUsage",
    "SnapshotRecord",
    "ValidationResult",
    "WorkspaceFinding",
    "CacheInfo",
    "WorkspaceProvenance",
    "ALL_SOURCES",
    "ALL_QUALITY_RULES",
    "ALL_VERDICTS",
    "ALL_ACTIONS",
    "VERDICT_READY",
    "VERDICT_READY_WITH_WARNINGS",
    "VERDICT_NOT_READY",
    "VERDICT_DENIED",
]
