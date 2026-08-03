"""Intelligent Architecture Compliance Engine package (Specification 037)."""

from .architecture_compliance_engine import ArchitectureComplianceEngine
from .report_data import (
    ArchitectureComplianceReport, ComplianceUnit, ArchitectureViolation,
    RefactoringSuggestion, ComplianceFinding, CacheInfo, ComplianceProvenance,
    ALL_SOURCES, ALL_QUALITY_RULES, ALL_VERDICTS, MIN_COMPLIANCE_SCORE,
    VERDICT_READY, VERDICT_READY_WITH_WARNINGS, VERDICT_NOT_READY,
)

__all__ = [
    "ArchitectureComplianceEngine",
    "ArchitectureComplianceReport",
    "ComplianceUnit",
    "ArchitectureViolation",
    "RefactoringSuggestion",
    "ComplianceFinding",
    "CacheInfo",
    "ComplianceProvenance",
    "ALL_SOURCES",
    "ALL_QUALITY_RULES",
    "ALL_VERDICTS",
    "MIN_COMPLIANCE_SCORE",
    "VERDICT_READY",
    "VERDICT_READY_WITH_WARNINGS",
    "VERDICT_NOT_READY",
]
