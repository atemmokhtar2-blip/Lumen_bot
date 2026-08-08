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
from ..registry.discovery import discover_and_register
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
    # Auto-discover and register all engines defined in discovery.py
    discover_and_register(registry)

    registry.register_builder(DirectoryBuilder())
    registry.register_builder(FileBuilder())
    registry.register_builder(PythonModuleBuilder())

    registry.register_validator(BlueprintValidator())
    registry.register_validator(StructureValidator())

    manager = CoreEngineManager(config=config)
    for engine in registry.engines():
        eid = getattr(engine, "engine_id", None) or getattr(engine, "name", engine.__class__.__name__)
        manager.register(engine, engine_id=eid)
    output_manager = OutputManager()
    orchestrator = PipelineOrchestrator(registry=registry, output_manager=output_manager, config=config, manager=manager)
    return registry, orchestrator, manager
