"""
Core bootstrap — hybrid engine assembly.

Kept: Formal + Planning + Reviews + Performance + Git/Repo engines.
"""

from __future__ import annotations

from typing import Optional

from ..builders import DirectoryBuilder, FileBuilder, PythonModuleBuilder
from ..configuration import ConfigSource, Configuration
from ..configuration.defaults import build_default_schema
from ..engines.generators import (
    FormalUnderstandingEngine,
    FormalGenerationEngine,
    ProjectPlanningEngine,
    ProjectStructurePlanningEngine,
    ExecutionPlanningEngine,
    ArchitectureDecisionEngine,
    TechnologySelectionEngine,
    RiskDetectionEngine,
    GenerationReadinessEngine,
    GenerationStrategyEngine,
    CodeGenerationPlanningEngine,
    StructureGenerationEngine,
    FileGenerationPlanningEngine,
    DependencyResolutionEngine,
    ProjectContextEngine,
    ComponentDetectionEngine,
    SecurityReviewEngine,
    PerformanceOptimizationEngine,
    ArchitectureComplianceEngine,
    CodeOptimizationEngine,
    CodeRefactoringEngine,
    StaticAnalysisEngine,
    UnitTestGenerationEngine,
    ProjectCapabilityAnalyzerEngine,
    BlueprintValidatorEngine,
    GitOperationsEngine,
    RepositoryManagementEngine,
    WorkspaceManagementEngine,
    FileSystemEngine,
    LiveDeploymentEngine,
)
from ..logging import EngineLogger
from ..manager import CoreEngineManager
from ..output import OutputManager
from ..pipeline import PipelineOrchestrator
from ..registry import EngineRegistry
from ..validators import BlueprintValidator, StructureValidator


def build_configuration(sources: Optional[list] = None) -> Configuration:
    schema = build_default_schema()
    if sources is None:
        sources = [ConfigSource(name="defaults")]
    return Configuration(schema=schema, sources=sources)


def bootstrap(
    config: Optional[Configuration] = None,
    sources: Optional[list] = None,
) -> tuple:
    if config is None:
        config = build_configuration(sources=sources)

    EngineLogger.configure(config)
    registry = EngineRegistry()

    registry.register_builder(DirectoryBuilder())
    registry.register_builder(FileBuilder())
    registry.register_builder(PythonModuleBuilder())

    # Formal core
    registry.register_engine(FormalUnderstandingEngine())
    registry.register_engine(FormalGenerationEngine())

    # Planning
    registry.register_engine(ProjectPlanningEngine())
    registry.register_engine(BlueprintValidatorEngine())
    registry.register_engine(StructureGenerationEngine())
    registry.register_engine(ComponentDetectionEngine())
    registry.register_engine(FileGenerationPlanningEngine())
    registry.register_engine(DependencyResolutionEngine())
    registry.register_engine(ProjectContextEngine())
    registry.register_engine(ArchitectureDecisionEngine())
    registry.register_engine(TechnologySelectionEngine())
    registry.register_engine(ProjectCapabilityAnalyzerEngine())
    registry.register_engine(RiskDetectionEngine())
    registry.register_engine(ExecutionPlanningEngine())
    registry.register_engine(ProjectStructurePlanningEngine())
    registry.register_engine(GenerationStrategyEngine())
    registry.register_engine(GenerationReadinessEngine())
    registry.register_engine(CodeGenerationPlanningEngine())

    # Reviews & optimization
    registry.register_engine(SecurityReviewEngine())
    registry.register_engine(PerformanceOptimizationEngine())
    registry.register_engine(ArchitectureComplianceEngine())
    registry.register_engine(CodeOptimizationEngine())
    registry.register_engine(CodeRefactoringEngine())
    registry.register_engine(StaticAnalysisEngine())
    registry.register_engine(UnitTestGenerationEngine())

    # Git / repo / workspace
    registry.register_engine(GitOperationsEngine())
    registry.register_engine(RepositoryManagementEngine())
    registry.register_engine(WorkspaceManagementEngine())
    registry.register_engine(FileSystemEngine())
    registry.register_engine(LiveDeploymentEngine())

    registry.register_validator(BlueprintValidator())
    registry.register_validator(StructureValidator())

    manager = CoreEngineManager(config=config)
    for engine in registry.engines():
        manager.register(engine, engine_id=getattr(engine, "engine_id", engine.__class__.__name__))
    output_manager = OutputManager()
    orchestrator = PipelineOrchestrator(registry=registry, output_manager=output_manager, config=config, manager=manager)
    return registry, orchestrator, manager
