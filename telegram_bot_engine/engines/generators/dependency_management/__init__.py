"""Intelligent Dependency & Package Management Engine package (Specification 050)."""

from .dependency_management_engine import DependencyManagementEngine
from .report_data import (
    DependencyManagementReport, Dependency, Conflict, SecurityIssue,
    HealthScore, LockEntry, RegistryEntry, DepFinding, CacheInfo, DepProvenance,
    ALL_SOURCES, ALL_QUALITY_RULES, ALL_VERDICTS,
    VERDICT_READY, VERDICT_READY_WITH_WARNINGS, VERDICT_NOT_READY,
)

__all__ = [
    "DependencyManagementEngine",
    "DependencyManagementReport",
    "Dependency",
    "Conflict",
    "SecurityIssue",
    "HealthScore",
    "LockEntry",
    "RegistryEntry",
    "DepFinding",
    "CacheInfo",
    "DepProvenance",
    "ALL_SOURCES",
    "ALL_QUALITY_RULES",
    "ALL_VERDICTS",
    "VERDICT_READY",
    "VERDICT_READY_WITH_WARNINGS",
    "VERDICT_NOT_READY",
]
