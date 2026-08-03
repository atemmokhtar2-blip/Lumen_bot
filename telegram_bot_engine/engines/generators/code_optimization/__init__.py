"""Intelligent Code Optimization Engine package (Specification 034)."""

from .code_optimization_engine import CodeOptimizationEngine
from .report_data import (
    CodeOptimizationReport, OptimizedUnit, OptimizationAction,
    OptimizationIssue, OptimizationFinding, CacheInfo, OptimizationProvenance,
    ALL_SOURCES, ALL_QUALITY_RULES, ALL_VERDICTS, MIN_QUALITY_SCORE,
    VERDICT_READY, VERDICT_READY_WITH_WARNINGS, VERDICT_NOT_READY,
)

__all__ = [
    "CodeOptimizationEngine",
    "CodeOptimizationReport",
    "OptimizedUnit",
    "OptimizationAction",
    "OptimizationIssue",
    "OptimizationFinding",
    "CacheInfo",
    "OptimizationProvenance",
    "ALL_SOURCES",
    "ALL_QUALITY_RULES",
    "ALL_VERDICTS",
    "MIN_QUALITY_SCORE",
    "VERDICT_READY",
    "VERDICT_READY_WITH_WARNINGS",
    "VERDICT_NOT_READY",
]
