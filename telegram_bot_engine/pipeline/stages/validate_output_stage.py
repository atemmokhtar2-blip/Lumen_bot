"""
Validate output stage — checks the generated files after generation.

This stage runs every validator whose ``applies_to`` metadata includes
``"output"``.  It verifies that the generated files exist, are
syntactically valid, and are consistent with the blueprint.
"""

from __future__ import annotations

from typing import List

from ...core.context import GenerationContext
from ...core.result import StageResult, ValidationReport
from ...registry import EngineRegistry
from ..base_stage import BaseStage


class ValidateOutputStage(BaseStage):
    """Validates the generated project files."""

    stage_name = "validate_output"
    requires: List[str] = ["generated_files"]
    provides: List[str] = ["output_validation_reports"]

    def __init__(self, registry: EngineRegistry) -> None:
        super().__init__()
        self._registry = registry

    def execute(self, context: GenerationContext) -> StageResult:
        validators = self._registry.validators()
        reports: List[ValidationReport] = []
        errors: List[str] = []
        warnings: List[str] = []

        for validator in validators:
            meta = getattr(validator, "metadata", {}) or {}
            applies = meta.get("applies_to", [])
            if applies and "output" not in applies:
                continue
            try:
                report = validator.validate(context)
            except Exception as exc:  # noqa: BLE001
                errors.append(f"Validator '{validator.name}' crashed: {exc}")
                continue
            reports.append(report)
            errors.extend(report.errors)
            warnings.extend(report.warnings)

        context.set("output_validation_reports", reports)

        # Soft-fail when files already exist on disk so PackageStage can run.
        has_files = bool(getattr(context, "created_files", None))
        if errors and not has_files:
            return StageResult.failed(
                self.name,
                errors=errors,
                warnings=warnings,
                metadata={"validator_count": len(reports)},
            )
        if errors:
            warnings = list(warnings) + list(errors)
            errors = []
        return StageResult.ok(
            self.name,
            outputs={"reports": reports},
            warnings=warnings,
            metadata={"validator_count": len(reports)},
        )


__all__ = ["ValidateOutputStage"]
