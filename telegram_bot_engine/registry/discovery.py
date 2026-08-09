"""
Auto-discovery of real generation engines.

Registers the concrete engine implementations (not stubs).
Priority and dependency metadata are applied later by the manager
in bootstrap (or by the caller of register).

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
    ArchitectureComplianceEngine,
    ArchitectureDecisionEngine,
    BlueprintValidatorEngine,
    CodeGenerationPlanningEngine,
    CodeOptimizationEngine,
    CodeRefactoringEngine,
    ComponentDetectionEngine,
    DependencyResolutionEngine,
    ExecutionPlanningEngine,
    FileGenerationPlanningEngine,
    FileSystemEngine,
    FormalGenerationEngine,
    FormalUnderstandingEngine,
    GenerationReadinessEngine,
    GenerationStrategyEngine,
    GitOperationsEngine,
    LiveDeploymentEngine,
    PerformanceOptimizationEngine,
    ProjectCapabilityAnalyzerEngine,
    ProjectContextEngine,
    ProjectPlanningEngine,
    ProjectStructurePlanningEngine,
    RepositoryManagementEngine,
    RiskDetectionEngine,
    SecurityReviewEngine,
    StaticAnalysisEngine,
    StructureGenerationEngine,
    TechnologySelectionEngine,
    UnitTestGenerationEngine,
    WorkspaceManagementEngine,
)


# Canonical ordered list of real engine classes.
# Order here is documentation only; actual execution order is controlled
# by priority + dependencies passed to CoreEngineManager.register().
ENGINE_CLASSES: List[Type[Engine]] = [
    FormalUnderstandingEngine,
    ProjectContextEngine,
    ProjectCapabilityAnalyzerEngine,
    ProjectPlanningEngine,
    ArchitectureDecisionEngine,
    TechnologySelectionEngine,
    RiskDetectionEngine,
    ProjectStructurePlanningEngine,
    GenerationStrategyEngine,
    CodeGenerationPlanningEngine,
    FileGenerationPlanningEngine,
    ExecutionPlanningEngine,
    DependencyResolutionEngine,
    StructureGenerationEngine,
    FormalGenerationEngine,
    FileSystemEngine,
    WorkspaceManagementEngine,
    StaticAnalysisEngine,
    SecurityReviewEngine,
    CodeOptimizationEngine,
    CodeRefactoringEngine,
    PerformanceOptimizationEngine,
    ArchitectureComplianceEngine,
    UnitTestGenerationEngine,
    BlueprintValidatorEngine,
    GenerationReadinessEngine,
    ComponentDetectionEngine,
    GitOperationsEngine,
    RepositoryManagementEngine,
    LiveDeploymentEngine,
]


def discover_and_register(registry: EngineRegistry) -> None:
    """Instantiate and register every real engine into the registry."""
    for cls in ENGINE_CLASSES:
        engine = cls()
        registry.register_engine(engine)


def get_engine_classes() -> List[Type[Engine]]:
    """Return the ordered list of engine classes (for tests / tooling)."""
    return list(ENGINE_CLASSES)
