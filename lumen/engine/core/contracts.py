"""
Contracts — the abstract interfaces every engine component must honour.

This module is the backbone of the modular architecture.  It defines
four primary contracts:

* :class:`Component` — base for anything that has a name, version, and
  metadata.  All engines, builders, and validators are components.
* :class:`Engine` — a generation engine that transforms inputs into
  outputs (e.g. ``BlueprintComposerEngine``, ``HandlerGeneratorEngine``).
* :class:`Builder` — a low-level file/folder/code creator used by
  generators to materialise artefacts on disk.
* :class:`PipelineStage` — a single step in the generation pipeline.

The contracts are intentionally minimal.  Concrete implementations live
in their own modules and register themselves with the
:class:`~lumen.engine.registry.EngineRegistry`.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Dict, List, Optional

from .result import StageResult, ValidationReport

if TYPE_CHECKING:
    from ..configuration.config import Configuration
    from .context import GenerationContext


# ---------------------------------------------------------------------------
# Component metadata
# ---------------------------------------------------------------------------

@dataclass
class Component:
    """Base class for every addressable engine component.

    Every component declares an identity (name, version) and a set of
    metadata that the registry uses for discovery and ordering.
    """

    name: str
    version: str = "1.0.0"
    description: str = ""
    tags: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.name:
            raise ValueError("A component must have a non-empty name.")


# ---------------------------------------------------------------------------
# Engine contract
# ---------------------------------------------------------------------------

class Engine(ABC, Component):
    """A generation engine.

    Self-declaration (required):
      declared_engine_id, declared_priority, declared_dependencies, declared_role
    Core bootstrap COLLECTS metadata; it does not hard-code every engine.
    """

    declared_engine_id: Optional[str] = None
    declared_priority: int = 100
    declared_dependencies: List[str] = []
    declared_role: str = "generation"

    @abstractmethod
    def execute(self, context: "GenerationContext") -> StageResult:
        """Run the engine and return a :class:`StageResult`.

        Implementations should:

        * Read required inputs from ``context``.
        * Write outputs back to ``context`` artefacts.
        * Return a :class:`StageResult` describing the outcome.
        * Raise on unrecoverable failures only.
        """
        raise NotImplementedError

    def initialize(self, config: "Configuration") -> None:
        """Optional hook called once after registration.

        Default implementation does nothing.  Override to read engine
        specific configuration.
        """

    def shutdown(self) -> None:
        """Optional hook called when the engine is being torn down."""

    def get_engine_id(self) -> str:
        return self.declared_engine_id or self.name

    def get_priority(self) -> int:
        return int(self.declared_priority)

    def get_dependencies(self) -> List[str]:
        return list(self.declared_dependencies or [])

    def get_role(self) -> str:
        return self.declared_role or "generation"



# ---------------------------------------------------------------------------
# Builder contract
# ---------------------------------------------------------------------------

class Builder(ABC, Component):
    """A low-level builder that materialises artefacts on disk.

    Builders are the only components allowed to create files and
    directories on the output filesystem.  Generators delegate the
    physical writing to builders so that generators stay focused on
    *what* to produce, while builders handle *how* it is written.

    Examples of builders:

    * ``DirectoryBuilder`` — creates folder structures.
    * ``FileBuilder`` — writes a single file.
    * ``PythonModuleBuilder`` — writes a Python module with a header.
    """

    @abstractmethod
    def build(self, context: "GenerationContext",
              spec: Dict[str, Any]) -> StageResult:
        """Materialise the artefact described by *spec*.

        ``spec`` is a dictionary that the builder understands.  The
        return value reports success and lists the files created.
        """
        raise NotImplementedError

    def initialize(self, config: "Configuration") -> None:
        """Optional hook called once after registration."""


# ---------------------------------------------------------------------------
# Validator contract
# ---------------------------------------------------------------------------

class Validator(ABC, Component):
    """A validator that checks an aspect of the generation output.

    Validators run after engines (or after the whole pipeline) to ensure
    the generated artefacts are correct.  A validator returns a
    :class:`ValidationReport` — it never raises on warnings, only on
    internal failures.

    The pipeline decides whether to stop based on the report.
    """

    @abstractmethod
    def validate(self, context: "GenerationContext") -> ValidationReport:
        """Inspect the context and return a :class:`ValidationReport`."""
        raise NotImplementedError

    def initialize(self, config: "Configuration") -> None:
        """Optional hook called once after registration."""


# ---------------------------------------------------------------------------
# Pipeline stage contract
# ---------------------------------------------------------------------------

class PipelineStage(ABC, Component):
    """A single stage in the generation pipeline.

    A stage wraps one or more engines/validators and is responsible for:

    * Checking that its preconditions are met (it has the inputs it needs).
    * Executing its component(s).
    * Returning a :class:`StageResult` so the pipeline can continue.

    Stages are ordered by the pipeline orchestrator.  They must declare
    their required artefact keys so the orchestrator can detect missing
    inputs before running.
    """

    requires: List[str] = field(default_factory=list)
    provides: List[str] = field(default_factory=list)

    @abstractmethod
    def run(self, context: "GenerationContext") -> StageResult:
        """Execute the stage."""
        raise NotImplementedError

    def check_preconditions(self, context: "GenerationContext") -> bool:
        """Return ``True`` when all required artefacts are present."""
        return all(context.has(key) for key in self.requires)


# Make the class-level ``requires``/``provides`` default properly for
# subclasses that don't redefine them.
PipelineStage.requires = []
PipelineStage.provides = []


__all__ = [
    "Component",
    "Engine",
    "Builder",
    "Validator",
    "PipelineStage",
]
