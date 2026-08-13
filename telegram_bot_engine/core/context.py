"""
Generation context — the shared state that flows through the pipeline.

The :class:`GenerationContext` is the only object that travels from one
pipeline stage to the next.  It carries:

* The user's original request (the bot description).
* The assembled :class:`~telegram_bot_engine.blueprint.Blueprint` (once the
  composer stage has run).
* The working directory where files are written.
* A free-form ``artefacts`` dictionary where stages can store intermediate
  outputs for later stages.
* A reference to the engine :class:`Configuration`.

Stages never communicate with each other directly; they read from and
write to the context.  This keeps the pipeline decoupled and testable.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any, Dict, Optional

if TYPE_CHECKING:
    from ..configuration.config import Configuration
    from ..blueprint.blueprint import Blueprint


@dataclass
class GenerationContext:
    """Mutable container for the state of a single generation run."""

    request: str
    config: "Configuration"
    work_dir: Path
    run_id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    blueprint: Optional["Blueprint"] = None
    artefacts: Dict[str, Any] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)
    created_files: list = field(default_factory=list)

    # -- artefact helpers --------------------------------------------------

    def set(self, key: str, value: Any) -> None:
        """Store an intermediate artefact produced by a stage."""
        self.artefacts[key] = value

    def get(self, key: str, default: Any = None) -> Any:
        return self.artefacts.get(key, default)

    def has(self, key: str) -> bool:
        return key in self.artefacts

    # -- file tracking -----------------------------------------------------

    def track_file(self, path: str) -> None:
        """Record a file that was created during the generation."""
        if path not in self.created_files:
            self.created_files.append(path)

    # -- blueprint helpers -------------------------------------------------

    def attach_blueprint(self, blueprint: "Blueprint") -> None:
        self.blueprint = blueprint

    @property
    def has_blueprint(self) -> bool:
        return self.blueprint is not None


__all__ = ["GenerationContext"]
