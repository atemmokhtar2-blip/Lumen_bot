"""
Core bootstrap — hybrid engine assembly.

Kept: Formal + Planning + Reviews + Performance + Git/Repo engines.

STRICT RULE (project-wide, non-negotiable):
  No pre-baked bot templates, saved tool packs, static command sets,
  or any ready-made bot structures. Every artefact is generated
  dynamically and exclusively from the user's natural-language text
  via SpecTranslator → formal/DSL path. Nothing is stored as a
  reusable "bot template".
"""

from __future__ import annotations

from typing import Dict, List, Optional, Tuple

from ..builders import DirectoryBuilder, FileBuilder, PythonModuleBuilder
from ..configuration import ConfigSource, Configuration
from ..configuration.defaults import build_default_schema
from ..logging import EngineLogger
from ..manager import CoreEngineManager
from ..output import OutputManager
from ..pipeline import PipelineOrchestrator
from ..registry import EngineRegistry
from ..registry.discovery import discover_and_register
from ..validators import BlueprintValidator, StructureValidator


# ---------------------------------------------------------------------------
# Priority + dependency map (lower priority number runs first)
# Dependencies are engine_ids (the .name of each engine).
# ---------------------------------------------------------------------------
# Groups:
#   10-29  Understanding / Context
#   30-59  Planning / Architecture
#   60-89  Generation planning
#   90-119 Generation
#   120-159 Reviews / Optimisation
#   160+   Validation / Repo / Live
ENGINE_META: Dict[str, Tuple[int, List[str]]] = {
    # Understanding & context
    "formal_understanding": (10, []),
    "project_context": (15, ["formal_understanding"]),
    "capability_analyzer": (20, ["project_context"]),
    # Planning
    "project_planner": (30, ["capability_analyzer"]),
    "architecture_decision": (35, ["project_planner"]),
    "technology_selection": (40, ["architecture_decision"]),
    "risk_detection": (45, ["technology_selection"]),
    "project_structure_planning": (50, ["risk_detection"]),
    # Generation strategy & planning
    "generation_strategy": (60, ["project_structure_planning"]),
    "code_generation_planning": (65, ["generation_strategy"]),
    "file_planner": (70, ["code_generation_planning"]),
    "execution_planning": (75, ["file_planner"]),
    "dependency_resolver": (80, ["execution_planning"]),
    # Actual generation
    "structure_generator": (90, ["dependency_resolver"]),
    "formal_generation": (100, ["structure_generator"]),
    "file_system": (105, ["formal_generation"]),
    "workspace_management": (110, ["file_system"]),
    # Reviews & optimisation
    "static_analysis": (120, ["workspace_management"]),
    "security_review": (125, ["static_analysis"]),
    "code_optimization": (130, ["security_review"]),
    "code_refactoring": (135, ["code_optimization"]),
    "performance_optimization": (140, ["code_refactoring"]),
    "architecture_compliance": (145, ["performance_optimization"]),
    "unit_test_generation": (150, ["architecture_compliance"]),
    # Validation & readiness
    "blueprint_validator": (160, ["unit_test_generation"]),
    "generation_readiness": (170, ["blueprint_validator"]),
    "component_detector": (175, ["generation_readiness"]),
    # Repo & live
    "git_operations": (180, ["component_detector"]),
    "repository_management": (185, ["git_operations"]),
    "live_deployment": (200, ["repository_management"]),
}


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
    # Auto-discover and register all *real* engines defined in discovery.py
    discover_and_register(registry)

    registry.register_builder(DirectoryBuilder())
    registry.register_builder(FileBuilder())
    registry.register_builder(PythonModuleBuilder())

    registry.register_validator(BlueprintValidator())
    registry.register_validator(StructureValidator())

    manager = CoreEngineManager(config=config)
    for engine in registry.engines():
        eid = getattr(engine, "engine_id", None) or getattr(
            engine, "name", engine.__class__.__name__
        )
        priority, deps = ENGINE_META.get(eid, (100, []))
        manager.register(
            engine,
            engine_id=eid,
            priority=priority,
            dependencies=deps,
            enabled=True,
        )
    output_manager = OutputManager()
    orchestrator = PipelineOrchestrator(
        registry=registry,
        output_manager=output_manager,
        config=config,
        manager=manager,
    )
    return registry, orchestrator, manager
