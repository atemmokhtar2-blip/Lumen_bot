"""
Base engine — shared boilerplate for engine implementations.

Concrete engines inherit from :class:`BaseEngine` to get a logger and
helpers to build :class:`StageResult` objects consistently.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from ...core.contracts import Engine
from ...core.result import StageResult
from ...logging import get_logger


class BaseEngine(Engine):
    """Convenience base class for engine implementations."""

    def __init__(self, name: str, version: str = "1.0.0",
                 description: str = "", tags: Optional[List[str]] = None,
                 metadata: Optional[Dict[str, Any]] = None) -> None:
        super().__init__(
            name=name,
            version=version,
            description=description,
            tags=tags or [],
            metadata=metadata or {},
        )
        self._log = get_logger(f"engine.{name}")

    def ok(self, outputs: Optional[Dict[str, Any]] = None,
           metadata: Optional[Dict[str, Any]] = None) -> StageResult:
        return StageResult.ok(self.name, outputs=outputs, metadata=metadata)

    def failed(self, errors: List[str],
               outputs: Optional[Dict[str, Any]] = None,
               warnings: Optional[List[str]] = None) -> StageResult:
        return StageResult.failed(
            self.name, errors=errors, outputs=outputs, warnings=warnings
        )

    def execute(self, context):  # type: ignore[override]
        raise NotImplementedError(
            f"Engine '{self.name}' must implement execute()."
        )


__all__ = ["BaseEngine"]
