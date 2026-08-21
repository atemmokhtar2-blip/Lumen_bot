"""
Core bootstrap — assembles engines without hard-coding their knowledge.
Each Engine self-declares engine_id, priority, dependencies, role.
"""

from __future__ import annotations

from typing import List, Optional, Tuple

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
from ..planes.control import ControlPlane
from ..planes.runtime import RuntimePlane
from ..security.policy import PolicyEngine
from ..security.sandbox import SandboxExecutor


def build_configuration(sources: Optional[list] = None) -> Configuration:
    schema = build_default_schema()
    if sources is None:
        sources = [ConfigSource(name="defaults")]
    return Configuration(schema=schema, sources=sources)


def _resolve_engine_meta(engine) -> Tuple[str, int, List[str], str]:
    eid = engine.get_engine_id() if hasattr(engine, "get_engine_id") else (
        getattr(engine, "name", engine.__class__.__name__)
    )
    priority = engine.get_priority() if hasattr(engine, "get_priority") else 100
    deps = list(engine.get_dependencies()) if hasattr(engine, "get_dependencies") else []
    role = engine.get_role() if hasattr(engine, "get_role") else "generation"
    return eid, int(priority), deps, role


def bootstrap(
    config: Optional[Configuration] = None,
    sources: Optional[list] = None,
) -> tuple:
    if config is None:
        config = build_configuration(sources=sources)

    EngineLogger.configure(config)
    registry = EngineRegistry()
    discover_and_register(registry)

    registry.register_builder(DirectoryBuilder())
    registry.register_builder(FileBuilder())
    registry.register_builder(PythonModuleBuilder())
    registry.register_validator(BlueprintValidator())
    registry.register_validator(StructureValidator())

    manager = CoreEngineManager(config=config)
    for engine in registry.engines():
        eid, priority, deps, role = _resolve_engine_meta(engine)
        if hasattr(engine, "declared_role"):
            engine.declared_role = role
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

    control = ControlPlane()
    runtime = RuntimePlane(policy=PolicyEngine(), sandbox=SandboxExecutor())
    orchestrator.control_plane = control  # type: ignore[attr-defined]
    orchestrator.runtime_plane = runtime  # type: ignore[attr-defined]
    manager.control_plane = control  # type: ignore[attr-defined]
    manager.runtime_plane = runtime  # type: ignore[attr-defined]

    return registry, orchestrator, manager
