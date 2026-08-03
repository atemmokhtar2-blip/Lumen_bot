"""Intelligent Performance Optimization Engine package (Specification 036)."""

from .performance_optimization_engine import PerformanceOptimizationEngine
from .report_data import (
    PerformanceReport, PerfUnit, Bottleneck, PerformanceAction,
    LoadSimulation, CachePlan, PerformanceFinding, CacheInfo,
    PerformanceProvenance,
    ALL_SOURCES, ALL_QUALITY_RULES, ALL_VERDICTS, MIN_QUALITY_SCORE,
    VERDICT_READY, VERDICT_READY_WITH_WARNINGS, VERDICT_NOT_READY,
)

__all__ = [
    "PerformanceOptimizationEngine",
    "PerformanceReport",
    "PerfUnit",
    "Bottleneck",
    "PerformanceAction",
    "LoadSimulation",
    "CachePlan",
    "PerformanceFinding",
    "CacheInfo",
    "PerformanceProvenance",
    "ALL_SOURCES",
    "ALL_QUALITY_RULES",
    "ALL_VERDICTS",
    "MIN_QUALITY_SCORE",
    "VERDICT_READY",
    "VERDICT_READY_WITH_WARNINGS",
    "VERDICT_NOT_READY",
]
