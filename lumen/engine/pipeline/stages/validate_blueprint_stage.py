"""
Validate blueprint stage — checks the blueprint before generation.

This stage runs every registered validator whose ``applies_to`` metadata
includes ``"blueprint"``.  Each validator returns a
:class:`~core.result.ValidationReport`; the stage aggregates them and
fails if any report contains errors.
"""

from __future__ import annotations

from typing import List

from ...core.context import GenerationContext
from ...core.result import StageResult, ValidationReport
from ...registry import EngineRegistry
from ..base_stage import BaseStage


class ValidateBlueprintStage(BaseStage):
    """Validates the assembled blueprint."""

    stage_name = "validate_blueprint"
    requires: List[str] = ["blueprint"]
    provides: List[str] = []

    def __init__(self, registry: EngineRegistry) -> None:
        super().__init__()
        self._registry = registry

    def execute(self, context: GenerationContext) -> StageResult:
        if context.blueprint is None:
            return StageResult.failed(
                self.name, ["No blueprint attached to the context."]
            )

        validators = self._registry.validators()
        reports: List[ValidationReport] = []
        errors: List[str] = []
        warnings: List[str] = []

        for validator in validators:
            meta = getattr(validator, "metadata", {}) or {}
            applies = meta.get("applies_to", [])
            # When ``applies_to`` is empty the validator is considered global.
            if applies and "blueprint" not in applies:
                continue
            try:
                report = validator.validate(context)
            except Exception as exc:  # noqa: BLE001
                errors.append(
                    f"Validator '{validator.name}' crashed: {exc}"
                )
                continue
            reports.append(report)
            errors.extend(report.errors)
            warnings.extend(report.warnings)

        context.set("blueprint_validation_reports", reports)

        if errors:
            return StageResult.failed(
                self.name,
                errors=errors,
                warnings=warnings,
                metadata={"validator_count": len(reports)},
            )
        return StageResult.ok(
            self.name,
            outputs={"reports": reports},
            warnings=warnings,
            metadata={"validator_count": len(reports)},
        )


__all__ = ["ValidateBlueprintStage"]
