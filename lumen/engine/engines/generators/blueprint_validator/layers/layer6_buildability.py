"""
Layer 6 — Buildability Validation (Specification 005).

The sixth and final validation layer checks that the project can
actually be built and that all the information required for generation
is present.  It is the "final gate" before the blueprint is approved.

This layer validates:

* **Structure entries** — the expected structure must have at least a
  root and some entries (warning when entries are very few).
* **Required engines** — the blueprint should declare the required
  generation engines for the phases (warning when missing).
* **Libraries** — the project identity should declare at least one
  library (the framework) (warning when empty).
* **Bot type** — the bot type should be a non-empty, recognised string
  (warning when it is 'general' or empty, which may indicate the
  analysis was inconclusive).
* **Missing information** — the blueprint's risks of kind ``"missing"``
  are collected and converted to :class:`MissingInformationFinding`
  objects.  Required missing information causes an error.
* **Risks summary** — the blueprint's risks of kind ``"error"`` severity
  are flagged.  If any error-severity risks remain, the blueprint is
  not buildable.
* **Blueprint ready flag** — the blueprint's ``ready`` flag should be
  ``True`` (error when it is not and there are no other error findings).
"""

from __future__ import annotations

import time
from typing import List

from ..validation_report import (
    LAYER_6_BUILDABILITY,
    LayerResult,
    MissingInformationFinding,
)
from ...project_planner.blueprint import ProjectBlueprint


class Layer6Buildability:
    """Layer 6: validates the overall buildability of the project.

    The layer is stateless; it receives a :class:`ProjectBlueprint` and
    returns a :class:`LayerResult`.
    """

    #: The human-readable name of this layer.
    name: str = "Buildability Validation"

    def validate(self, blueprint: ProjectBlueprint) -> LayerResult:
        """Run all buildability checks and return the layer result."""
        start = time.perf_counter()
        result = LayerResult(
            layer_id=LAYER_6_BUILDABILITY,
            name=self.name,
        )

        # --- Structure entries -------------------------------------------
        structure = blueprint.structure
        if not structure.entries:
            result.add_warning(
                code="no_structure_entries",
                message=(
                    "The expected structure has no entries.  The "
                    "project structure is not defined."
                ),
                affected="structure.entries",
                resolution_hint=(
                    "Add structure entries for the project layout."
                ),
            )
        elif len(structure.entries) < 3:
            result.add_warning(
                code="thin_structure",
                message=(
                    f"The expected structure has only "
                    f"{len(structure.entries)} entries.  A more "
                    f"complete structure is recommended."
                ),
                affected="structure.entries",
                resolution_hint=(
                    "Add more structure entries to describe the project "
                    "layout."
                ),
            )

        # --- Required engines --------------------------------------------
        if not blueprint.required_engines:
            result.add_warning(
                code="no_required_engines",
                message=(
                    "The blueprint does not declare any required "
                    "generation engines."
                ),
                affected="required_engines",
                resolution_hint=(
                    "Declare the engines needed for each phase."
                ),
            )

        # --- Libraries ---------------------------------------------------
        if not blueprint.identity.libraries:
            result.add_warning(
                code="no_libraries",
                message=(
                    "No libraries were declared in the project "
                    "identity.  At least the framework library is "
                    "expected."
                ),
                affected="identity.libraries",
                resolution_hint=(
                    "Add the framework and required libraries to the "
                    "project identity."
                ),
            )

        # --- Bot type ----------------------------------------------------
        bot_type = (blueprint.identity.bot_type or "").strip()
        if not bot_type or bot_type == "general":
            result.add_warning(
                code="generic_bot_type",
                message=(
                    f"The bot type is '{bot_type}', which is the "
                    f"default.  This may indicate the analysis was "
                    f"inconclusive."
                ),
                affected="identity.bot_type",
                resolution_hint=(
                    "Refine the analysis to determine a more specific "
                    "bot type."
                ),
            )

        # --- Missing information from risks ------------------------------
        for risk in blueprint.risks:
            if risk.kind == "missing":
                required = risk.severity == "error"
                if required:
                    result.add_error(
                        code="missing_required_information",
                        message=risk.description,
                        affected=risk.affected,
                        resolution_hint=(
                            risk.resolution_hint or
                            "Provide the missing information."
                        ),
                    )
                else:
                    result.add_warning(
                        code="missing_information",
                        message=risk.description,
                        affected=risk.affected,
                        resolution_hint=(
                            risk.resolution_hint or
                            "Provide the missing information when "
                            "available."
                        ),
                    )

        # --- Error-severity risks ----------------------------------------
        error_risks = [
            r for r in blueprint.risks
            if r.severity == "error" and r.kind != "missing"
        ]
        for risk in error_risks:
            result.add_error(
                code=f"risk_{risk.kind}",
                message=risk.description,
                affected=risk.affected,
                resolution_hint=(
                    risk.resolution_hint or "Resolve the risk."
                ),
            )

        # --- Blueprint ready flag ----------------------------------------
        if not blueprint.ready and not result.findings:
            # If nothing else caught it, flag that the blueprint's own
            # validation failed.
            result.add_error(
                code="blueprint_not_ready",
                message=(
                    "The blueprint's 'ready' flag is False, "
                    "indicating it failed its own internal validation."
                ),
                affected="ready",
                resolution_hint=(
                    "Review the blueprint's internal validation "
                    "errors and resolve them."
                ),
            )

        result.duration_ms = (time.perf_counter() - start) * 1000
        return result


__all__ = ["Layer6Buildability"]
