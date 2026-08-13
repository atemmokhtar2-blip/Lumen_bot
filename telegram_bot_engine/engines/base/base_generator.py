"""
Base generator — convenience base for generator engines.

Generators differ from plain engines in that they produce files using
builders.  :class:`BaseGenerator` holds references to the common
builders (directory, file, python module) so generators can request
file creation without looking them up each time.

Generators receive the builders at initialisation time from the
:func:`~telegram_bot_engine.core.bootstrap` function, which keeps the
dependency wiring in a single place.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from ...builders import DirectoryBuilder, FileBuilder, PythonModuleBuilder
from ...core.context import GenerationContext
from ...core.result import StageResult
from .base_engine import BaseEngine


class BaseGenerator(BaseEngine):
    """Convenience base class for generator engines."""

    def __init__(self, name: str,
                 directory_builder: DirectoryBuilder,
                 file_builder: FileBuilder,
                 python_module_builder: PythonModuleBuilder,
                 version: str = "1.0.0",
                 description: str = "",
                 tags: Optional[List[str]] = None,
                 metadata: Optional[Dict[str, Any]] = None,
                 order: int = 100) -> None:
        super().__init__(
            name=name, version=version,
            description=description, tags=tags, metadata=metadata,
        )
        self._directory_builder = directory_builder
        self._file_builder = file_builder
        self._python_module_builder = python_module_builder
        # Store the ordering hint in metadata so the generate stage can sort.
        self.metadata["order"] = order

    # -- builder helpers ---------------------------------------------------

    def create_dirs(self, context: GenerationContext,
                    paths: List[str]) -> StageResult:
        return self._directory_builder.build(
            context, {"paths": paths}
        )

    def write_file(self, context: GenerationContext,
                   path: str, content: str,
                   overwrite: bool = True) -> StageResult:
        return self._file_builder.build(
            context,
            {"path": path, "content": content, "overwrite": overwrite},
        )

    def write_python_module(self, context: GenerationContext,
                           path: str, module_doc: str, code: str,
                           overwrite: bool = True) -> StageResult:
        return self._python_module_builder.build(
            context,
            {
                "path": path,
                "module_doc": module_doc,
                "code": code,
                "overwrite": overwrite,
            },
        )


__all__ = ["BaseGenerator"]
