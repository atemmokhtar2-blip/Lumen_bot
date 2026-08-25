"""
Layer 4 — Execution Plan Validation (Specification 005).

The fourth validation layer checks that the execution plan is
complete, well-ordered, and logical.  It validates:

* **All eight phases present** — the plan must contain all eight
  default phases (project_setup through export).  Missing phases are
  errors.
* **Contiguous numbering** — the phase numbers must be 1..N with no
  gaps.  Non-contiguous numbering is an error.
* **Phase order** — phases must appear in the correct order (sorted by
  number).  Out-of-order phases are errors.
* **Every phase has tasks** — every phase must have at least one
  component, feature, or engine assigned, unless it is explicitly
  skippable.  An empty, non-skippable phase is a warning.
* **Phase names unique** — no two phases may share the same name
  (error when they do).
* **Order locked** — the plan's ``order_locked`` flag should be ``True``
  (warning when it is not).
"""

from __future__ import annotations

import time
from typing import List, Set

from ..validation_report import (
    LAYER_4_EXECUTION_PLAN,
    LayerResult,
)
from ...project_planner.execution_plan import (
    DEFAULT_PHASES,
    ExecutionPlan,
)
from ...project_planner.blueprint import ProjectBlueprint


class Layer4ExecutionPlan:
    """Layer 4: validates the execution plan.

    The layer is stateless; it receives a :class:`ProjectBlueprint` and
    returns a :class:`LayerResult`.
    """

    #: The human-readable name of this layer.
    name: str = "Execution Plan Validation"

    def validate(self, blueprint: ProjectBlueprint) -> LayerResult:
        """Run all execution-plan checks and return the layer result."""
        start = time.perf_counter()
        result = LayerResult(
            layer_id=LAYER_4_EXECUTION_PLAN,
            name=self.name,
        )

        plan = blueprint.execution_plan

        # --- No phases at all --------------------------------------------
        if not plan.phases:
            result.add_error(
                code="no_phases",
                message=(
                    "The execution plan contains no phases."
                ),
                affected="execution_plan",
                resolution_hint=(
                    "Build the execution plan with all eight phases."
                ),
            )
            result.duration_ms = (time.perf_counter() - start) * 1000
            return result

        # --- All eight phases present ------------------------------------
        expected_names = {p.name for p in DEFAULT_PHASES}
        actual_names = {p.name for p in plan.phases}
        missing = expected_names - actual_names
        if missing:
            result.add_error(
                code="missing_phases",
                message=(
                    f"The execution plan is missing phase(s): "
                    f"{sorted(missing)}."
                ),
                affected=", ".join(sorted(missing)),
                resolution_hint=(
                    "Add the missing phase(s) to the execution plan."
                ),
            )

        # --- Phase name uniqueness ---------------------------------------
        seen: Set[str] = set()
        for phase in plan.phases:
            if phase.name in seen:
                result.add_error(
                    code="duplicate_phase_name",
                    message=(
                        f"Phase name '{phase.name}' is used more than "
                        f"once."
                    ),
                    affected=phase.name,
                    resolution_hint="Rename the duplicate phase.",
                )
            else:
                seen.add(phase.name)

        # --- Contiguous numbering ----------------------------------------
        if not plan.phases_are_contiguous():
            numbers = sorted(p.number for p in plan.phases)
            result.add_error(
                code="non_contiguous_phases",
                message=(
                    f"Phase numbers are not contiguous.  Found "
                    f"{numbers}, expected 1..{len(numbers)}."
                ),
                affected="execution_plan",
                resolution_hint=(
                    "Renumber the phases so they are contiguous 1..N."
                ),
            )

        # --- Phase order --------------------------------------------------
        phase_numbers = [p.number for p in plan.phases]
        if phase_numbers != sorted(phase_numbers):
            result.add_error(
                code="phases_out_of_order",
                message=(
                    "Phases are not in ascending order by number."
                ),
                affected="execution_plan",
                resolution_hint=(
                    "Reorder the phases so their numbers ascend."
                ),
            )

        # --- Every phase has tasks (or is skippable) --------------------
        for phase in plan.phases:
            has_tasks = (
                bool(phase.components)
                or bool(phase.features)
                or bool(phase.engines)
            )
            if not has_tasks and not phase.skippable:
                result.add_warning(
                    code="empty_phase",
                    message=(
                        f"Phase {phase.number} '{phase.name}' has no "
                        f"components, features, or engines assigned."
                    ),
                    affected=phase.name,
                    resolution_hint=(
                        f"Assign tasks to phase '{phase.name}' or mark "
                        f"it as skippable."
                    ),
                )

        # --- Order locked -------------------------------------------------
        if not plan.order_locked:
            result.add_warning(
                code="order_not_locked",
                message=(
                    "The execution plan's order is not locked.  The "
                    "phase order may be changed unexpectedly."
                ),
                affected="execution_plan",
                resolution_hint="Lock the execution plan order.",
            )

        result.duration_ms = (time.perf_counter() - start) * 1000
        return result


__all__ = ["Layer4ExecutionPlan"]
