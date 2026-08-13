"""
Auto-discovery of real generation engines.

Formal understanding / formal generation removed permanently.
"""

from __future__ import annotations

from typing import List, Type

from .registry import EngineRegistry
from ..core.contracts import Engine
from ..engines.generators import (
    ProjectPlanningEngine,
    ProjectStructurePlanningEngine,
    WorkspaceManagementEngine,
    FileSystemEngine,
    DependencyResolutionEngine,
    RepositoryManagementEngine,
    GitOperationsEngine,
    BlueprintValidatorEngine,
    ComponentDetectionEngine,
    FileGenerationPlanningEngine,
    StructureGenerationEngine,
)


ENGINE_CLASSES: List[Type[Engine]] = [
    ProjectPlanningEngine,
    ProjectStructurePlanningEngine,
    StructureGenerationEngine,
    FileGenerationPlanningEngine,
    DependencyResolutionEngine,
    FileSystemEngine,
    WorkspaceManagementEngine,
    BlueprintValidatorEngine,
    ComponentDetectionEngine,
    GitOperationsEngine,
    RepositoryManagementEngine,
]


def discover_and_register(registry: EngineRegistry) -> None:
    """Instantiate and register every real engine into the registry."""
    for cls in ENGINE_CLASSES:
        engine = cls()
        registry.register_engine(engine)


def get_engine_classes() -> List[Type[Engine]]:
    """Return the ordered list of engine classes (for tests / tooling)."""
    return list(ENGINE_CLASSES)
