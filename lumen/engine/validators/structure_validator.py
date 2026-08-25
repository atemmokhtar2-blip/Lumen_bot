"""
Structure validator — checks the generated project file structure.

This validator runs during the ``validate_output`` stage.  It verifies
that the expected top-level files exist, that Python files are
syntactically valid (by compiling them), and that no empty directories
were left behind.
"""

from __future__ import annotations

import py_compile
from pathlib import Path

from ..core.context import GenerationContext
from ..core.result import ValidationReport
from .base_validator import BaseValidator

# Minimum set of files every generated project should contain.
_REQUIRED_FILES = [
    "main.py",
    "config.py",
    "requirements.txt",
    "README.md",
]


class StructureValidator(BaseValidator):
    """Validates the file structure of the generated project."""

    def __init__(self) -> None:
        super().__init__(
            name="structure_validator",
            description="Validates the generated project file structure.",
            applies_to=["output"],
            tags=["validation"],
        )

    def validate(self, context: GenerationContext) -> ValidationReport:
        report = self.report()
        work_dir: Path = context.work_dir

        # -- required files --------------------------------------------------
        for required in _REQUIRED_FILES:
            target = work_dir / required
            if not target.exists():
                report.add_error(f"Missing required file: {required}")

        # -- python syntax ---------------------------------------------------
        for py_file in work_dir.rglob("*.py"):
            try:
                py_compile.compile(str(py_file), doraise=True)
            except py_compile.PyCompileError as exc:
                report.add_error(
                    f"Syntax error in {py_file.relative_to(work_dir)}: {exc.msg}"
                )
            except Exception as exc:  # noqa: BLE001
                report.add_error(
                    f"Failed to compile {py_file.relative_to(work_dir)}: {exc}"
                )

        # -- empty directories ----------------------------------------------
        for path in work_dir.rglob("*"):
            if path.is_dir() and not any(path.iterdir()):
                report.add_warning(
                    f"Empty directory: {path.relative_to(work_dir)}"
                )

        # -- no files at all -------------------------------------------------
        all_files = [p for p in work_dir.rglob("*") if p.is_file()]
        if not all_files:
            report.add_error("No files were generated.")

        if report.passed:
            self._log.info("Structure validation passed",
                           {"files": len(all_files)})
        else:
            self._log.warning("Structure validation failed",
                              {"errors": len(report.errors)})

        return report


__all__ = ["StructureValidator"]
