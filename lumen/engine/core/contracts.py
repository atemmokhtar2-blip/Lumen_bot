"""Shared base types for engine components.

Legacy Engine / Builder / Validator / PipelineStage contracts that powered the
deterministic catalog pipeline were removed with that pipeline.
Generation is Cline-only (see engine_router / cline_runtime).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List


@dataclass
class Component:
    """Lightweight named component identity (tools, gates, etc.)."""

    name: str
    version: str = "1.0.0"
    description: str = ""
    tags: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.name:
            raise ValueError("A component must have a non-empty name.")


__all__ = ["Component"]
