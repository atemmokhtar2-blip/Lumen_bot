"""
Blueprint Validator Engine (Specification 005).

The :class:`BlueprintValidatorEngine` is the gatekeeper that decides
whether a :class:`ProjectBlueprint` may proceed to the building phase.
It does **not** generate code, create files, or modify the blueprint.
Its sole function is to validate the blueprint through six independent
layers, detect conflicts, compute a quality score, and produce an
authoritative approval verdict.

Data source
-----------
The engine reads **only** the ``project_blueprint`` artefact from the
generation context (produced by the
:class:`~telegram_bot_engine.engines.generators.project_planner.ProjectPlanningEngine`).
It does **not** read the user's request or the analysis report.

Responsibility
--------------
* Validate the blueprint through six layers.
* Detect conflicts that make the project impossible or incorrect.
* Compute a quality score for the blueprint.
* Produce an APPROVED or REJECTED verdict.
* Log every test, result, warning, error, and the review duration.

Output
------
The final output is a
:class:`~telegram_bot_engine.engines.generators.blueprint_validator.validation_report.BlueprintValidationReport`,
stored in the context as the ``blueprint_validation_report`` artefact.
No generation engine may proceed until this report's ``status`` is
``APPROVED``.

Approval rules
--------------
The blueprint is **APPROVED** when:

1. All six layers passed (no errors in any layer).
2. No error-severity conflicts were detected.
3. The quality score meets or exceeds the minimum required threshold.

Otherwise the report's ``status`` is ``REJECTED`` with a detailed list
of all the reasons.
"""

from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from ....core.context import GenerationContext
from ....core.result import StageResult
from ...base.base_engine import BaseEngine
from .conflict_detector import ConflictDetector
from .quality_scorer import QualityScorer
from .validation_report import (
    ALL_LAYERS,
    BlueprintValidationReport,
    ConflictFinding,
    MissingInformationFinding,
    QualityScore,
    SEVERITY_ERROR,
    SEVERITY_WARNING,
    STATUS_APPROVED,
    STATUS_REJECTED,
)
from .layers import (
    Layer1BasicData,
    Layer2Features,
    Layer3Relationships,
    Layer4ExecutionPlan,
    Layer5Dependencies,
    Layer6Buildability,
)
from ..project_planner.blueprint import (
    BlueprintRisk,
    ProjectBlueprint,
)


# ---------------------------------------------------------------------------#
# The engine
# ---------------------------------------------------------------------------#

class BlueprintValidatorEngine(BaseEngine):
    """The gatekeeper that validates a :class:`ProjectBlueprint`.

    This engine reads the ``project_blueprint`` artefact from the
    context, runs six validation layers, detects conflicts, computes a
    quality score, and produces a
    :class:`BlueprintValidationReport` stored as the
    ``blueprint_validation_report`` artefact.

    The engine is forbidden from reading the user's request or the
    analysis report.  It reads only the blueprint.
    """

    def __init__(self) -> None:
        super().__init__(
            name="blueprint_validator",
            version="1.0.0",
            description=(
                "Validates the ProjectBlueprint through six layers, "
                "detects conflicts, computes a quality score, and "
                "produces an APPROVED/REJECTED verdict.  Does not "
                "generate code or create files."
            ),
            tags=["validation", "blueprint"],
            metadata={"phase": "validation"},
        )
        self._layers = [
            Layer1BasicData(),
            Layer2Features(),
            Layer3Relationships(),
            Layer4ExecutionPlan(),
            Layer5Dependencies(),
            Layer6Buildability(),
        ]
        self._conflict_detector = ConflictDetector()
        self._quality_scorer = QualityScorer()

    # -----------------------------------------------------------------#
    # Main entry point
    # -----------------------------------------------------------------#

    def execute(self, context: GenerationContext) -> StageResult:
        """Validate the blueprint and produce a validation report."""
        review_start = time.perf_counter()

        # Step 0: obtain the blueprint — the only data source.
        blueprint = context.get("project_blueprint")
        if blueprint is None:
            return self.failed([
                "No 'project_blueprint' artefact found. The Blueprint "
                "Validator Engine requires the Project Planning Engine "
                "to have run first. The validator does not read the "
                "raw request."
            ])

        self._log.info(
            "Starting blueprint validation",
            {
                "blueprint_name": blueprint.identity.name,
                "features": len(blueprint.features),
                "components": len(blueprint.components),
                "layers": len(self._layers),
            },
        )

        # Build the report.
        report = BlueprintValidationReport(
            blueprint_name=blueprint.identity.name or "unnamed",
            reviewed_at=datetime.now(timezone.utc).isoformat(),
        )

        # Step 1: run all six validation layers.
        for layer in self._layers:
            self._log.info(
                f"Running layer: {layer.name}",
                {"layer_id": layer.name},
            )
            layer_result = layer.validate(blueprint)
            report.add_layer(layer_result)
            self._log.info(
                f"Layer completed: {layer.name}",
                {
                    "passed": layer_result.passed,
                    "errors": layer_result.error_count,
                    "warnings": layer_result.warning_count,
                    "duration_ms": round(layer_result.duration_ms, 2),
                },
            )
            if layer_result.error_count > 0:
                for err in layer_result.errors:
                    self._log.error(
                        f"Layer {layer.name} error: {err.message}",
                        {
                            "code": err.code,
                            "affected": err.affected,
                        },
                    )
            if layer_result.warning_count > 0:
                for warn in layer_result.warnings:
                    self._log.warning(
                        f"Layer {layer.name} warning: {warn.message}",
                        {
                            "code": warn.code,
                            "affected": warn.affected,
                        },
                    )

        # Step 2: detect conflicts.
        self._log.info("Detecting conflicts", {})
        conflicts = self._conflict_detector.detect(blueprint)
        report.conflicts = conflicts
        conflict_errors = [
            c for c in conflicts if c.severity == SEVERITY_ERROR
        ]
        conflict_warnings = [
            c for c in conflicts if c.severity == SEVERITY_WARNING
        ]
        self._log.info(
            "Conflict detection completed",
            {
                "total": len(conflicts),
                "errors": len(conflict_errors),
                "warnings": len(conflict_warnings),
            },
        )
        for c in conflict_errors:
            self._log.error(
                f"Conflict: {c.description}",
                {"kind": c.kind, "affected": c.affected},
            )
        for c in conflict_warnings:
            self._log.warning(
                f"Conflict: {c.description}",
                {"kind": c.kind, "affected": c.affected},
            )

        # Step 3: collect missing information from the blueprint risks.
        missing_info: List[MissingInformationFinding] = []
        for risk in blueprint.risks:
            if risk.kind == "missing":
                missing_info.append(MissingInformationFinding(
                    field=risk.affected or "unknown",
                    description=risk.description,
                    question=risk.resolution_hint or "",
                    required=risk.severity == SEVERITY_ERROR,
                ))
        report.missing_info = missing_info

        # Step 4: compute the quality score.
        total_errors = report.error_count + len(conflict_errors)
        total_warnings = report.warning_count + len(conflict_warnings)
        self._log.info(
            "Computing quality score",
            {
                "error_count": total_errors,
                "warning_count": total_warnings,
            },
        )
        quality = self._quality_scorer.score(
            blueprint,
            error_count=total_errors,
            warning_count=total_warnings,
        )
        report.quality = quality
        self._log.info(
            "Quality score computed",
            {
                "overall": round(quality.overall, 4),
                "minimum_required": round(quality.minimum_required, 4),
                "meets_minimum": quality.meets_minimum,
            },
        )

        # Step 5: compute the total review duration.
        report.total_duration_ms = (time.perf_counter() - review_start) * 1000

        # Step 6: determine the approval verdict.
        all_layers_passed = report.all_layers_passed
        no_conflict_errors = len(conflict_errors) == 0
        quality_meets_minimum = quality.meets_minimum
        no_required_missing = all(
            not m.required for m in missing_info
        )

        if all_layers_passed and no_conflict_errors and quality_meets_minimum:
            report.status = STATUS_APPROVED
        else:
            report.status = STATUS_REJECTED

        # Build a human-readable summary.
        report.summary = self._build_summary(
            report, all_layers_passed, no_conflict_errors,
            quality_meets_minimum, no_required_missing,
        )

        # Store the report in the context.
        context.set("blueprint_validation_report", report)
        context.metadata["blueprint_validation_report"] = report

        self._log.info(
            "Blueprint validation complete",
            {
                "status": report.status,
                "all_layers_passed": all_layers_passed,
                "conflict_errors": len(conflict_errors),
                "quality_meets_minimum": quality_meets_minimum,
                "total_duration_ms": round(report.total_duration_ms, 2),
            },
        )

        if report.is_approved:
            return self.ok(
                outputs={"blueprint_validation_report": report},
                metadata={
                    "status": report.status,
                    "quality_score": round(quality.overall, 4),
                    "errors": report.error_count,
                    "warnings": report.warning_count,
                    "duration_ms": round(report.total_duration_ms, 2),
                },
            )

        # Rejected — collect all error messages for the StageResult.
        error_messages: List[str] = []
        for layer_result in report.layers.values():
            for err in layer_result.errors:
                error_messages.append(
                    f"[{layer_result.name}] {err.message}"
                )
        for c in conflict_errors:
            error_messages.append(c.description)
        if not quality_meets_minimum:
            error_messages.append(
                f"Quality score {round(quality.overall, 4)} is below "
                f"the minimum required {round(quality.minimum_required, 4)}."
            )
        for m in missing_info:
            if m.required:
                error_messages.append(
                    f"Missing required information: {m.description}"
                )

        return self.failed(
            errors=error_messages or [
                "Blueprint validation failed for unknown reasons."
            ],
            outputs={"blueprint_validation_report": report},
            warnings=[w.message for w in report.warnings],
        )

    # -----------------------------------------------------------------#
    # Helpers
    # -----------------------------------------------------------------#

    @staticmethod
    def _build_summary(
        report: BlueprintValidationReport,
        all_layers_passed: bool,
        no_conflict_errors: bool,
        quality_meets_minimum: bool,
        no_required_missing: bool,
    ) -> str:
        """Build a human-readable summary of the validation verdict."""
        parts: List[str] = []
        if report.is_approved:
            parts.append("APPROVED")
        else:
            parts.append("REJECTED")
        parts.append(f"— {report.error_count} error(s), "
                     f"{report.warning_count} warning(s).")
        if not all_layers_passed:
            failed_layers = [
                lr.name for lr in report.layers.values() if not lr.passed
            ]
            parts.append(f"Failed layers: {failed_layers}.")
        if not no_conflict_errors:
            parts.append(f"Conflict errors: "
                         f"{sum(1 for c in report.conflicts if c.severity == SEVERITY_ERROR)}.")
        if not quality_meets_minimum:
            parts.append(f"Quality score {round(report.quality.overall, 4)} "
                         f"< minimum {round(report.quality.minimum_required, 4)}.")
        if not no_required_missing:
            required_missing = [m for m in report.missing_info if m.required]
            parts.append(f"Required missing info: {len(required_missing)}.")
        return " ".join(parts)


__all__ = ["BlueprintValidatorEngine"]
