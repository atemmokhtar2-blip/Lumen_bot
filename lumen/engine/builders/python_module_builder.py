"""
Python module builder — writes a Python module with a consistent header.

The builder delegates the physical writing to :class:`FileBuilder` but
prepends a standardised module header (docstring) so that every
generated Python file starts with a description of its responsibility.

This keeps the "one responsibility per file" rule visible in the
generated code itself.
"""

from __future__ import annotations

from typing import Any, Dict

from ..core.contracts import Builder
from ..core.context import GenerationContext
from ..core.result import StageResult
from ..logging import get_logger
from .file_builder import FileBuilder

_logger = get_logger("builder.python_module")


class PythonModuleBuilder(Builder):
    """Writes a Python module with a standardised header docstring."""

    def __init__(self) -> None:
        super().__init__(
            name="python_module_builder",
            version="1.0.0",
            description="Writes Python modules with a standard header.",
            tags=["io", "python"],
        )
        self._file_builder = FileBuilder()

    def build(self, context: GenerationContext,
              spec: Dict[str, Any]) -> StageResult:
        """Write a Python module.

        Expected ``spec`` keys:

        * ``path`` (str): destination path relative to the work directory.
        * ``module_doc`` (str): the module docstring (one paragraph).
        * ``code`` (str): the module body (without the header docstring).
        * ``overwrite`` (bool, optional).
        """
        path = spec.get("path")
        module_doc = spec.get("module_doc", "")
        code = spec.get("code", "")

        if not path:
            return StageResult.failed(
                self.name, ["PythonModuleBuilder requires a 'path' in spec."]
            )

        header = self._format_header(module_doc)
        full_content = f"{header}\n\n{code.rstrip()}\n"

        file_spec = {
            "path": path,
            "content": full_content,
            "overwrite": spec.get("overwrite", True),
            "base": spec.get("base"),
        }
        result = self._file_builder.build(context, file_spec)
        if not result.success:
            return result

        _logger.debug(
            "Wrote python module",
            {"path": result.outputs.get("path"), "doc": module_doc[:60]},
        )
        return StageResult.ok(
            self.name,
            outputs={
                "path": result.outputs.get("path"),
                "module_doc": module_doc,
            },
        )

    @staticmethod
    def _format_header(module_doc: str) -> str:
        lines = [line for line in module_doc.strip().splitlines() if line.strip()]
        if not lines:
            body = ""
        elif len(lines) == 1:
            body = lines[0]
        else:
            body = "\n".join(lines)
        return f'"""{body}\n"""'


__all__ = ["PythonModuleBuilder"]
