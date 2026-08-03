"""Intelligent Static Analysis Engine package (Specification 039)."""

from .static_analysis_engine import StaticAnalysisEngine
from .report_data import (
    StaticAnalysisReport, AnalyzedUnit, StaticIssue, RepairSuggestion,
    DependencyEdge, RiskItem, StaticFinding, CacheInfo, StaticProvenance,
    ALL_SOURCES, ALL_QUALITY_RULES, ALL_VERDICTS,
    VERDICT_READY, VERDICT_READY_WITH_WARNINGS, VERDICT_NOT_READY,
)

__all__ = [
    "StaticAnalysisEngine",
    "StaticAnalysisReport",
    "AnalyzedUnit",
    "StaticIssue",
    "RepairSuggestion",
    "DependencyEdge",
    "RiskItem",
    "StaticFinding",
    "CacheInfo",
    "StaticProvenance",
    "ALL_SOURCES",
    "ALL_QUALITY_RULES",
    "ALL_VERDICTS",
    "VERDICT_READY",
    "VERDICT_READY_WITH_WARNINGS",
    "VERDICT_NOT_READY",
]
