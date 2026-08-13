"""
Engine entry data model (Specification 003).

An :class:`EngineEntry` is the manager's record for a single engine.  It
augments the raw :class:`~core.contracts.Engine` instance with the
management metadata required by the Core Engine Manager:

* ``engine_id`` — a unique, stable identifier (no duplicates allowed).
* ``name`` — the human-readable engine name.
* ``version`` — the engine version string.
* ``status`` — the current :class:`~manager.lifecycle.EngineState`.
* ``priority`` — an integer controlling execution order (lower runs
  first).  Engines cannot change their own priority.
* ``dependencies`` — the set of engine IDs that must have completed
  successfully before this engine can run.
* ``enabled`` — whether the engine is enabled.  Disabled engines are
  registered but never loaded, initialized, or run.
* ``metadata`` — a free-form dictionary for extra information.

The entry is a plain data container.  It does **not** perform lifecycle
transitions — that is the manager's responsibility.  It only stores
state so the manager has a single source of truth.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Dict, FrozenSet, Optional, Set

if TYPE_CHECKING:
    from ..core.contracts import Engine

from .lifecycle import EngineState


@dataclass
class EngineMetadata:
    """Free-form metadata bag for an engine entry.

    This is separate from :class:`EngineEntry` so that the heavy
    metadata does not interfere with equality / hashing of the entry.
    """

    description: str = ""
    tags: list = field(default_factory=list)
    extra: Dict[str, Any] = field(default_factory=dict)


@dataclass
class EngineEntry:
    """The manager's record for a single registered engine.

    Attributes:
        engine_id: Unique, stable identifier for the engine.
        name: Human-readable name (mirrors the engine's component name).
        version: Version string (mirrors the engine's version).
        instance: The actual :class:`~core.contracts.Engine` object.
        status: Current lifecycle state.  Starts at ``REGISTERED``.
        priority: Execution priority.  Lower values run first.
        dependencies: Set of engine IDs that must complete before this
            engine can run.
        enabled: Whether the engine is enabled for execution.
        metadata: Optional :class:`EngineMetadata` for extra info.
        error: The reason the engine failed, if ``status`` is ``FAILED``.
        last_run_started_at: Timestamp (float seconds since epoch) when
            the engine last entered ``RUNNING``.
        last_run_finished_at: Timestamp when it left ``RUNNING``.
        last_duration_s: Duration of the last run in seconds.
    """

    engine_id: str
    name: str
    version: str
    instance: "Engine"
    status: EngineState = EngineState.REGISTERED
    priority: int = 100
    dependencies: Set[str] = field(default_factory=set)
    enabled: bool = True
    metadata: Optional[EngineMetadata] = None
    error: Optional[str] = None
    last_run_started_at: Optional[float] = None
    last_run_finished_at: Optional[float] = None
    last_duration_s: Optional[float] = None

    # -- convenience properties --------------------------------------------

    @property
    def is_registered(self) -> bool:
        return self.status == EngineState.REGISTERED

    @property
    def is_loaded(self) -> bool:
        return self.status == EngineState.LOADED

    @property
    def is_initialized(self) -> bool:
        return self.status == EngineState.INITIALIZED

    @property
    def is_ready(self) -> bool:
        return self.status == EngineState.READY

    @property
    def is_running(self) -> bool:
        return self.status == EngineState.RUNNING

    @property
    def is_completed(self) -> bool:
        return self.status == EngineState.COMPLETED

    @property
    def is_failed(self) -> bool:
        return self.status == EngineState.FAILED

    @property
    def is_terminal(self) -> bool:
        """``True`` when the engine is in a terminal state for this run."""
        return self.status in (EngineState.COMPLETED, EngineState.FAILED)

    def __post_init__(self) -> None:
        if not self.engine_id:
            raise ValueError("EngineEntry requires a non-empty engine_id.")
        if not self.name:
            raise ValueError("EngineEntry requires a non-empty name.")
        # Normalise dependencies to a set for fast membership tests.
        self.dependencies = set(self.dependencies)


__all__ = [
    "EngineEntry",
    "EngineMetadata",
]
