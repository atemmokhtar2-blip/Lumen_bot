"""Resource & Dependency Planning Engine package (Specification 025)."""

from .resource_dependency_planning_engine import ResourceDependencyPlanningEngine
from .report_data import (
    ResourceDependencyBlueprint, DependencyItem, ResourceItem,
    VersionMatrixEntry, RiskItem, OptimizationSuggestion,
    ResourceConflict, ResourceFinding, CacheInfo, ResourceProvenance,
    ALL_SOURCES, ALL_DEP_KINDS, ALL_RES_KINDS, ALL_QUALITY_RULES, ALL_VERDICTS,
    VERDICT_READY, VERDICT_READY_WITH_WARNINGS, VERDICT_NOT_READY,
)

__all__ = [
    "ResourceDependencyPlanningEngine",
    "ResourceDependencyBlueprint",
    "DependencyItem",
    "ResourceItem",
    "VersionMatrixEntry",
    "RiskItem",
    "OptimizationSuggestion",
    "ResourceConflict",
    "ResourceFinding",
    "CacheInfo",
    "ResourceProvenance",
    "ALL_SOURCES",
    "ALL_DEP_KINDS",
    "ALL_RES_KINDS",
    "ALL_QUALITY_RULES",
    "ALL_VERDICTS",
    "VERDICT_READY",
    "VERDICT_READY_WITH_WARNINGS",
    "VERDICT_NOT_READY",
]
