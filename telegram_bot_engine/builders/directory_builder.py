"""
Directory builder — creates folder structures on disk.

This is the *only* component in the engine that creates directories.
Every generator that needs a folder asks this builder to create it, so
that directory creation logic is centralised and consistent.

The builder tracks every directory it creates in the
:class:`~core.context.GenerationContext` so that later stages and
validators can inspect the structure.
"""

from __future__ import annotations

from typing import Any, Dict, List

from ..core.contracts import Builder
from ..core.context import GenerationContext
from ..core.result import StageResult
from ..logging import get_logger

_logger = get_logger("builder.directory")


class DirectoryBuilder(Builder):
    """Creates one or more directories relative to the work directory."""

    def __init__(self) -> None:
        super().__init__(
            name="directory_builder",
            version="1.0.0",
            description="Creates directory structures for generated projects.",
            tags=["io", "filesystem"],
        )

    def build(self, context: GenerationContext,
              spec: Dict[str, Any]) -> StageResult:
        """Create directories described by *spec*.

        Expected ``spec`` keys:

        * ``paths`` (list[str]): directories to create, relative to the
          work directory.  Parent directories are created automatically.
        * ``base`` (str, optional): override the base directory.
        """
        paths: List[str] = spec.get("paths", [])
        if not paths:
            return StageResult.ok(
                self.name,
                metadata={"created": []},
            )

        base_override = spec.get("base")
        base = context.work_dir
        if base_override:
            base = base / base_override

        created: List[str] = []
        errors: List[str] = []

        for rel_path in paths:
            target = base / rel_path
            try:
                target.mkdir(parents=True, exist_ok=True)
                rel_str = str(target.relative_to(context.work_dir))
                created.append(rel_str)
                context.track_file(rel_str)
                _logger.debug(
                    "Created directory",
                    {"path": rel_str},
                )
            except Exception as exc:  # noqa: BLE001
                errors.append(f"Failed to create directory '{rel_path}': {exc}")
                _logger.error(
                    "Failed to create directory",
                    {"path": str(rel_path), "error": str(exc)},
                )

        if errors:
            return StageResult.failed(self.name, errors, outputs={"created": created})
        return StageResult.ok(self.name, outputs={"created": created})


__all__ = ["DirectoryBuilder"]
