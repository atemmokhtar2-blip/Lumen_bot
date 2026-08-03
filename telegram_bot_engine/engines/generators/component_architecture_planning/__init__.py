"""Component Architecture Planning Engine package (Specification 022)."""

from .component_architecture_planning_engine import ComponentArchitecturePlanningEngine
from .report_data import (
    ComponentArchitectureBlueprint,
    ComponentDescriptor,
    ComponentInterface,
    ComponentRelation,
    ReuseOpportunity,
    ComponentConflict,
    ComponentFinding,
    CacheInfo,
    ComponentProvenance,
    ALL_SOURCES,
    ALL_KINDS,
    ALL_QUALITY_RULES,
    ALL_VERDICTS,
    VERDICT_READY,
    VERDICT_READY_WITH_WARNINGS,
    VERDICT_NOT_READY,
)

__all__ = [
    "ComponentArchitecturePlanningEngine",
    "ComponentArchitectureBlueprint",
    "ComponentDescriptor",
    "ComponentInterface",
    "ComponentRelation",
    "ReuseOpportunity",
    "ComponentConflict",
    "ComponentFinding",
    "CacheInfo",
    "ComponentProvenance",
    "ALL_SOURCES",
    "ALL_KINDS",
    "ALL_QUALITY_RULES",
    "ALL_VERDICTS",
    "VERDICT_READY",
    "VERDICT_READY_WITH_WARNINGS",
    "VERDICT_NOT_READY",
]
