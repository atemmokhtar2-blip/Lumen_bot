"""
Module Architecture Planning Engine package (Specification 021).
"""

from .module_architecture_planning_engine import ModuleArchitecturePlanningEngine
from .report_data import (
    ModuleArchitectureBlueprint,
    ModuleDescriptor,
    ModuleInterface,
    ModuleRelation,
    ArchitectureConflict,
    ArchitectureFinding,
    CacheInfo,
    ArchitectureProvenance,
    ALL_SOURCES,
    ALL_CATEGORIES,
    ALL_QUALITY_RULES,
    ALL_VERDICTS,
    VERDICT_READY,
    VERDICT_READY_WITH_WARNINGS,
    VERDICT_NOT_READY,
)

__all__ = [
    "ModuleArchitecturePlanningEngine",
    "ModuleArchitectureBlueprint",
    "ModuleDescriptor",
    "ModuleInterface",
    "ModuleRelation",
    "ArchitectureConflict",
    "ArchitectureFinding",
    "CacheInfo",
    "ArchitectureProvenance",
    "ALL_SOURCES",
    "ALL_CATEGORIES",
    "ALL_QUALITY_RULES",
    "ALL_VERDICTS",
    "VERDICT_READY",
    "VERDICT_READY_WITH_WARNINGS",
    "VERDICT_NOT_READY",
]
