"""
Core bootstrap — minimal working engine assembly.

Only engines that import successfully are kept:
  FormalUnderstanding, ProjectPlanning, ProjectStructurePlanning, FormalGeneration.

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
# Only engines that actually import and work are kept.
# ---------------------------------------------------------------------------
ENGINE_META: Dict[str, Tuple[int, List[str]]] = {
    "formal_understanding": (10, []),
    "project_planner": (30, ["formal_understanding"]),
    "project_structure_planning": (50, ["project_planner"]),
    "structure_generator": (90, ["project_structure_planning"]),
    "file_planner": (95, ["structure_generator"]),
    "dependency_resolver": (100, ["file_planner"]),
    "formal_generation": (110, ["dependency_resolver"]),
    "file_system": (120, ["formal_generation"]),
    "workspace_management": (130, ["file_system"]),
    "blueprint_validator": (140, ["workspace_management"]),
    "component_detector": (150, ["blueprint_validator"]),
    "git_operations": (180, ["formal_generation", "component_detector"]),
    "repository_management": (190, ["git_operations"]),
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
