"""
Pipeline orchestrator — drives the full generation lifecycle.

The orchestrator is the *only* component that knows the order of the
stages.  It builds the list of stages, passes the context through them,
collects results, and stops the pipeline on the first failing stage
(when ``fail_fast`` is enabled in the configuration).

The orchestrator is deliberately unaware of what each stage does — it
only calls ``stage.run(context)`` and inspects the returned
:class:`~core.result.StageResult`.
"""

from __future__ import annotations

from typing import List, Optional

from ..core.context import GenerationContext
from ..core.result import GenerationResult, StageResult
from ..logging import get_logger
from ..registry import EngineRegistry
from ..output import OutputManager
from .stages import (
    ComposeBlueprintStage,
    GenerateStage,
    MaterializeStage,
    PackageStage,
    ParseStage,
    ValidateBlueprintStage,
    ValidateOutputStage,
)

_logger = get_logger("pipeline.orchestrator")


class PipelineOrchestrator:
    """Drives the generation pipeline from request to packaged project."""

    def __init__(self, registry: EngineRegistry,
                 output_manager: OutputManager,
                 config=None,
                 manager=None) -> None:
        self._registry = registry
        self._output_manager = output_manager
        self._config = config
        self._manager = manager
        self._fail_fast = True
        if config is not None:
            self._fail_fast = bool(config.get("pipeline", "fail_fast", True))
        self._log = _logger

    def build_stages(self) -> List:
        """Construct and return the ordered list of pipeline stages."""
        return [
            ParseStage(self._registry),
            ComposeBlueprintStage(self._registry),
            ValidateBlueprintStage(self._registry),
            GenerateStage(self._registry, manager=self._manager),
            MaterializeStage(),
            ValidateOutputStage(self._registry),
            PackageStage(self._output_manager),
        ]

    def run(self, request: str, work_dir=None) -> GenerationResult:
        """Execute the full pipeline for a single request.

        Parameters:
            request: The user's natural-language bot description.
            work_dir: Optional override for the working directory.

        Returns:
            A :class:`GenerationResult` summarising the whole run.
        """
        from pathlib import Path

        if work_dir is None:
            base = "output"
            if self._config is not None:
                base = self._config.get("output", "base_dir", "output")
            work_dir = Path(base) / "current"
        else:
            work_dir = Path(work_dir)

        # Optionally clean the working directory before building.
        clean = True
        if self._config is not None:
            clean = bool(self._config.get("output", "clean_before_build", True))
        if clean and work_dir.exists():
            import shutil
            try:
                shutil.rmtree(work_dir)
            except OSError as exc:
                self._log.error(
                    "Failed to clean work_dir before build",
                    {"work_dir": str(work_dir), "error": f"{type(exc).__name__}: {exc}"},
                )
                raise RuntimeError(
                    f"work_dir_cleanup_failed:{work_dir}:{type(exc).__name__}:{exc}"
                ) from exc
        work_dir.mkdir(parents=True, exist_ok=True)

        context = GenerationContext(
            request=request,
            config=self._config,
            work_dir=work_dir,
        )

        self._log.info(
            "Pipeline starting",
            {"request": request, "work_dir": str(work_dir), "run_id": context.run_id},
        )

        stages = self.build_stages()
        stage_results: List[StageResult] = []
        errors: List[str] = []
        success = True

        for stage in stages:
            result = stage.run(context)
            stage_results.append(result)
            if not result.success:
                errors.extend(result.errors)
                success = False
                if self._fail_fast:
                    self._log.error(
                        "Pipeline stopping due to stage failure",
                        {"stage": result.stage_name},
                    )
                    break

        # Collect all validation reports from the context.
        validation_reports = []
        for key in ("blueprint_validation_reports", "output_validation_reports"):
            reports = context.get(key, [])
            if reports:
                validation_reports.extend(reports)

        final_project = context.get("final_project")
        project_path = final_project.get("project_path") if final_project else None

        result = GenerationResult(
            success=success,
            project_path=project_path,
            stages=stage_results,
            validation_reports=validation_reports,
            errors=errors,
            metadata={
                "run_id": context.run_id,
                "request": request,
                "files_created": list(context.created_files),
            },
        )

        if success:
            self._log.info(
                "Pipeline completed successfully",
                {"run_id": context.run_id,
                 "files": len(context.created_files),
                 "project_path": project_path},
            )
        else:
            self._log.error(
                "Pipeline completed with errors",
                {"run_id": context.run_id, "error_count": len(errors)},
            )

        return result


__all__ = ["PipelineOrchestrator"]
