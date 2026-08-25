"""
File builder — writes a single file to disk.

This is the *only* component that writes arbitrary file contents.  It
supports optional ``overwrite`` control and tracks every file it writes
in the :class:`~core.context.GenerationContext`.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from ..core.contracts import Builder
from ..core.context import GenerationContext
from ..core.result import StageResult
from ..logging import get_logger

_logger = get_logger("builder.file")


class FileBuilder(Builder):
    """Writes individual files relative to the work directory."""

    def __init__(self) -> None:
        super().__init__(
            name="file_builder",
            version="1.0.0",
            description="Writes individual files for generated projects.",
            tags=["io", "filesystem"],
        )

    def build(self, context: GenerationContext,
              spec: Dict[str, Any]) -> StageResult:
        """Write the file described by *spec*.

        Expected ``spec`` keys:

        * ``path`` (str): destination path relative to the work directory.
        * ``content`` (str): the file content.
        * ``overwrite`` (bool, optional, default False): whether to
          overwrite an existing file.  When ``False`` and the file
          exists, an error is returned.
        * ``base`` (str, optional): override the base directory.
        """
        path: Optional[str] = spec.get("path")
        content = spec.get("content", "")
        overwrite: bool = bool(spec.get("overwrite", False))
        base_override = spec.get("base")

        if not path:
            return StageResult.failed(
                self.name, ["FileBuilder requires a 'path' in spec."]
            )

        base = Path(context.work_dir).resolve()
        if base_override:
            # base_override must also stay under work_dir
            from lumen.engine.services.safe_fs import UnsafePathError, safe_resolve_under
            try:
                base = safe_resolve_under(Path(context.work_dir), str(base_override))
            except UnsafePathError as exc:
                return StageResult.failed(
                    self.name, [f"base path rejected: {exc}"]
                )

        from lumen.engine.services.safe_fs import UnsafePathError, safe_write_text

        # Containment: path is relative to base, base is under work_dir
        try:
            # First resolve relative to base as if base were root
            rel_for_check = str(path).replace("\\", "/").lstrip("/")
            target_preview = safe_resolve_under(base, rel_for_check)
        except UnsafePathError as exc:
            return StageResult.failed(
                self.name, [f"path rejected (traversal): {path}: {exc}"]
            )

        if target_preview.exists() and not overwrite:
            return StageResult.failed(
                self.name,
                [f"File already exists and overwrite is False: {path}"],
            )

        try:
            target = safe_write_text(base, rel_for_check, content if isinstance(content, str) else str(content))
            # Final containment vs original work_dir
            target.resolve().relative_to(Path(context.work_dir).resolve())
            rel_str = str(target.relative_to(Path(context.work_dir).resolve()))
            context.track_file(rel_str)
            _logger.debug("Wrote file", {"path": rel_str, "bytes": len(str(content))})
            return StageResult.ok(
                self.name,
                outputs={"path": rel_str, "bytes": len(str(content))},
            )
        except UnsafePathError as exc:
            return StageResult.failed(self.name, [f"write rejected: {exc}"])
        except Exception as exc:  # noqa: BLE001
            _logger.error("Failed to write file", {"path": path, "error": str(exc)})
            return StageResult.failed(
                self.name,
                [f"Failed to write file '{path}': {exc}"],
            )


__all__ = ["FileBuilder"]
