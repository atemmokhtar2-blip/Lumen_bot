"""
Project Structure Planning Engine package (Specification 020).
"""

from .project_structure_planning_engine import ProjectStructurePlanningEngine
from .report_data import (
    ProjectStructureBlueprint,
    FolderNode,
    FileDescriptor,
    ModuleMapping,
    FileDependency,
    StructureConflict,
    StructureFinding,
    CacheInfo,
    StructureProvenance,
    ALL_SOURCES,
    ALL_STANDARD_FOLDERS,
    ALL_FILE_TYPES,
    ALL_QUALITY_RULES,
    ALL_VERDICTS,
    VERDICT_READY,
    VERDICT_READY_WITH_WARNINGS,
    VERDICT_NOT_READY,
)

__all__ = [
    "ProjectStructurePlanningEngine",
    "ProjectStructureBlueprint",
    "FolderNode",
    "FileDescriptor",
    "ModuleMapping",
    "FileDependency",
    "StructureConflict",
    "StructureFinding",
    "CacheInfo",
    "StructureProvenance",
    "ALL_SOURCES",
    "ALL_STANDARD_FOLDERS",
    "ALL_FILE_TYPES",
    "ALL_QUALITY_RULES",
    "ALL_VERDICTS",
    "VERDICT_READY",
    "VERDICT_READY_WITH_WARNINGS",
    "VERDICT_NOT_READY",
]
