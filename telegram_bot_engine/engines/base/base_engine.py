"""
Base engine — shared boilerplate + self-declaration + role binding.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from ...core.contracts import Engine
from ...core.result import StageResult
from ...logging import get_logger


class BaseEngine(Engine):
    """Subclasses set declared_engine_id, declared_priority, declared_dependencies, declared_role."""

    def __init__(
        self,
        name: str,
        version: str = "1.0.0",
        description: str = "",
        tags: Optional[List[str]] = None,
        metadata: Optional[Dict[str, Any]] = None,
        *,
        engine_id: Optional[str] = None,
        priority: Optional[int] = None,
        dependencies: Optional[List[str]] = None,
        role: Optional[str] = None,
    ) -> None:
        super().__init__(
            name=name,
            version=version,
            description=description,
            tags=tags or [],
            metadata=metadata or {},
        )
        if engine_id is not None:
            self.declared_engine_id = engine_id
        if priority is not None:
            self.declared_priority = priority
        if dependencies is not None:
            self.declared_dependencies = list(dependencies)
        if role is not None:
            self.declared_role = role
        self._log = get_logger(f"engine.{name}")

    def ok(
        self,
        outputs: Optional[Dict[str, Any]] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> StageResult:
        return StageResult.ok(self.name, outputs=outputs, metadata=metadata)

    def failed(
        self,
        errors: List[str],
        outputs: Optional[Dict[str, Any]] = None,
        warnings: Optional[List[str]] = None,
    ) -> StageResult:
        return StageResult.failed(
            self.name, errors=errors, outputs=outputs, warnings=warnings
        )

    def execute(self, context):  # type: ignore[override]
        raise NotImplementedError(
            f"Engine '{self.name}' must implement execute()."
        )

    def bind_context_role(self, context) -> None:
        if hasattr(context, "set_active_role"):
            context.set_active_role(self.get_role())


__all__ = ["BaseEngine"]
