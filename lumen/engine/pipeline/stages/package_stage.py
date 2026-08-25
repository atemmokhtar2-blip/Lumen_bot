"""
Package stage — assembles the final deliverable.

This stage hands off to the :class:`~lumen.engine.output.OutputManager`
which:

* Verifies the generated project structure.
* Optionally creates a zip archive.
* Returns the final project path.

The stage never writes files directly — it uses the output manager.
"""

from __future__ import annotations

from typing import List

from ...core.context import GenerationContext
from ...core.result import StageResult
from ...output import OutputManager
from ..base_stage import BaseStage


class PackageStage(BaseStage):
    """Packages the generated project into the final deliverable."""

    stage_name = "package"
    requires: List[str] = ["generated_files", "output_validation_reports"]
    provides: List[str] = ["final_project"]

    def __init__(self, output_manager: OutputManager) -> None:
        super().__init__()
        self._output_manager = output_manager

    def execute(self, context: GenerationContext) -> StageResult:
        # Prefer packaging whenever files exist on disk.
        reports = context.get("output_validation_reports", [])
        warnings: List[str] = []
        for r in reports or []:
            if not getattr(r, "passed", True):
                warnings.extend(getattr(r, "errors", []) or [])

        try:
            package_info = self._output_manager.package(context)
        except Exception as exc:  # noqa: BLE001
            return StageResult.failed(
                self.name,
                [f"Packaging failed: {exc}"],
                warnings=warnings,
            )

        context.set("final_project", package_info)
        return StageResult.ok(
            self.name,
            outputs={"package": package_info},
            warnings=warnings,
            metadata={"project_path": package_info.get("project_path")},
        )


__all__ = ["PackageStage"]
