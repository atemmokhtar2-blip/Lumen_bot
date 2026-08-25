"""
Layer 2 — Features Validation (Specification 005).

The second validation layer checks that every feature in the blueprint
is properly described and that there are no duplicates or
inconsistencies.

This layer validates:

* **At least one feature** — the blueprint must contain at least one
  feature (error when the features list is empty).
* **Feature name** — every feature must have a non-empty, unique name.
  Duplicate names produce errors.
* **Feature description** — every feature should have a description
  (warning when missing).
* **Feature phase** — every feature should be assigned to an execution
  phase (warning when missing).
* **Feature display name** — every feature should have a display name
  (warning when missing).
* **Feature build priority** — the priority must be one of the known
  priority constants (warning when outside the expected range).
* **Feature depends-on-features** — a feature may not depend on itself
  (error); circular dependencies between features are detected by
  Layer 5.
"""

from __future__ import annotations

import time
from typing import List, Set

from ..validation_report import (
    LAYER_2_FEATURES,
    LayerResult,
)
from ...project_planner.feature_unit import (
    PRIORITY_CRITICAL,
    PRIORITY_HIGH,
    PRIORITY_NORMAL,
    PRIORITY_LOW,
    PRIORITY_DEFERRED,
    FeatureUnit,
)
from ...project_planner.blueprint import ProjectBlueprint


# Valid priority values.
_VALID_PRIORITIES = frozenset({
    PRIORITY_CRITICAL,
    PRIORITY_HIGH,
    PRIORITY_NORMAL,
    PRIORITY_LOW,
    PRIORITY_DEFERRED,
})


class Layer2Features:
    """Layer 2: validates the feature breakdown.

    The layer is stateless; it receives a :class:`ProjectBlueprint` and
    returns a :class:`LayerResult`.
    """

    #: The human-readable name of this layer.
    name: str = "Features Validation"

    def validate(self, blueprint: ProjectBlueprint) -> LayerResult:
        """Run all feature checks and return the layer result."""
        start = time.perf_counter()
        result = LayerResult(
            layer_id=LAYER_2_FEATURES,
            name=self.name,
        )

        features = blueprint.features

        # --- At least one feature ----------------------------------------
        if not features:
            result.add_error(
                code="no_features",
                message=(
                    "The blueprint contains no features.  At least one "
                    "feature is required."
                ),
                affected="features",
                resolution_hint="Add at least one feature to the blueprint.",
            )
            # No point checking individual features.
            result.duration_ms = (time.perf_counter() - start) * 1000
            return result

        # --- Duplicate detection -----------------------------------------
        seen: Set[str] = set()
        for unit in features:
            if unit.name in seen:
                result.add_error(
                    code="duplicate_feature",
                    message=(
                        f"Feature '{unit.name}' appears more than once "
                        f"in the blueprint."
                    ),
                    affected=unit.name,
                    resolution_hint=(
                        "Remove the duplicate feature or rename it."
                    ),
                )
            else:
                seen.add(unit.name)

        # --- Individual feature checks -----------------------------------
        for unit in features:
            # Feature name.
            if not unit.name:
                result.add_error(
                    code="missing_feature_name",
                    message="A feature has an empty name.",
                    affected="features",
                    resolution_hint="Set a non-empty name for every feature.",
                )

            # Feature description (warning).
            if not unit.description:
                result.add_warning(
                    code="missing_feature_description",
                    message=(
                        f"Feature '{unit.name}' has no description."
                    ),
                    affected=unit.name,
                    resolution_hint=(
                        f"Add a clear description for feature '{unit.name}'."
                    ),
                )

            # Feature display name (warning).
            if not unit.display_name:
                result.add_warning(
                    code="missing_display_name",
                    message=(
                        f"Feature '{unit.name}' has no display name."
                    ),
                    affected=unit.name,
                    resolution_hint=(
                        f"Add a human-readable display name for "
                        f"'{unit.name}'."
                    ),
                )

            # Feature phase (warning).
            if not unit.phase:
                result.add_warning(
                    code="missing_feature_phase",
                    message=(
                        f"Feature '{unit.name}' is not assigned to any "
                        f"execution phase."
                    ),
                    affected=unit.name,
                    resolution_hint=(
                        f"Assign '{unit.name}' to an execution phase."
                    ),
                )

            # Feature build priority (warning when invalid).
            if unit.build_priority not in _VALID_PRIORITIES:
                result.add_warning(
                    code="invalid_priority",
                    message=(
                        f"Feature '{unit.name}' has an unexpected build "
                        f"priority {unit.build_priority}.  Expected one "
                        f"of {sorted(_VALID_PRIORITIES)}."
                    ),
                    affected=unit.name,
                    resolution_hint=(
                        "Use one of the PRIORITY_* constants for the "
                        "build priority."
                    ),
                )

            # Self-dependency (error).
            if unit.name in unit.depends_on_features:
                result.add_error(
                    code="self_dependency",
                    message=(
                        f"Feature '{unit.name}' depends on itself."
                    ),
                    affected=unit.name,
                    resolution_hint=(
                        f"Remove the self-dependency from '{unit.name}'."
                    ),
                )

        result.duration_ms = (time.perf_counter() - start) * 1000
        return result


__all__ = ["Layer2Features"]
