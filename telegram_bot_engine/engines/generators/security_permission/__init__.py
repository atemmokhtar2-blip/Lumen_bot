"""Intelligent Security & Permission Management Engine (Specification 060)."""

from .security_permission_engine import SecurityPermissionEngine
from .report_data import (
    SecurityPermissionReport, PermissionGrant, RoleAssignment, AccessCheck,
    IsolationViolation, AuthRecord, SecurityAuditEntry, RecoveryAction,
    SecurityFinding, CacheInfo, SecurityProvenance,
    ALL_SOURCES, ALL_QUALITY_RULES, ALL_VERDICTS, ALL_ROLES, ALL_PERMISSIONS,
    VERDICT_READY, VERDICT_READY_WITH_WARNINGS, VERDICT_NOT_READY,
)

__all__ = [
    "SecurityPermissionEngine",
    "SecurityPermissionReport",
    "PermissionGrant",
    "RoleAssignment",
    "AccessCheck",
    "IsolationViolation",
    "AuthRecord",
    "SecurityAuditEntry",
    "RecoveryAction",
    "SecurityFinding",
    "CacheInfo",
    "SecurityProvenance",
    "ALL_SOURCES",
    "ALL_QUALITY_RULES",
    "ALL_VERDICTS",
    "ALL_ROLES",
    "ALL_PERMISSIONS",
    "VERDICT_READY",
    "VERDICT_READY_WITH_WARNINGS",
    "VERDICT_NOT_READY",
]
