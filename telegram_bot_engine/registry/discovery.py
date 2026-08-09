"""
Auto-discovery of real generation engines.

Only working engines are kept (formal core + git/push-pull chain + required supports).

STRICT RULE (enforced project-wide, non-negotiable):
  No pre-baked bot templates, saved tool packs, static command sets,
  or any ready-made bot structures. Every artefact is generated
  dynamically and exclusively from the user's natural-language text
  via SpecTranslator → formal/DSL path only. Nothing is stored as a
  reusable "bot template".
"""

from __future__ import annotations

from typing import List, Type

from .registry import EngineRegistry
from ..core.contracts import Engine
from ..engines.generators import (
    FormalUnderstandingEngine,
    FormalGenerationEngine,
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
    FormalUnderstandingEngine,
    ProjectPlanningEngine,
    ProjectStructurePlanningEngine,
    StructureGenerationEngine,
    FileGenerationPlanningEngine,
    DependencyResolutionEngine,
    FormalGenerationEngine,
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
