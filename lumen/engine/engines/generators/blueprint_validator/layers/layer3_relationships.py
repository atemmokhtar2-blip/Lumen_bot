"""
Layer 3 — Relationships Validation (Specification 005).

The third validation layer checks that every feature is connected to
the elements it depends on and that the component relationships are
well-formed.

This layer validates:

* **Feature-component connection** — every feature should introduce at
  least one component (warning when it does not).
* **Component-feature back-reference** — every component's
  ``source_feature`` should reference a real feature (warning when it
  does not).
* **Relationship endpoints** — every component relationship's source
  and target must be known components (error when they are not).
* **Duplicate relationships** — the same (source, target, kind) tuple
  should not appear more than once (warning when it does).
* **Feature dependency on features** — every feature's
  ``depends_on_features`` entries must reference real features (error).
* **Component dependency on components** — every component's
  ``dependencies`` entries must reference real components (error).
"""

from __future__ import annotations

import time
from typing import List, Set, Tuple

from ..validation_report import (
    LAYER_3_RELATIONSHIPS,
    LayerResult,
)
from ...project_planner.blueprint import (
    ComponentRelationship,
    ProjectBlueprint,
)


class Layer3Relationships:
    """Layer 3: validates feature and component relationships.

    The layer is stateless; it receives a :class:`ProjectBlueprint` and
    returns a :class:`LayerResult`.
    """

    #: The human-readable name of this layer.
    name: str = "Relationships Validation"

    def validate(self, blueprint: ProjectBlueprint) -> LayerResult:
        """Run all relationship checks and return the layer result."""
        start = time.perf_counter()
        result = LayerResult(
            layer_id=LAYER_3_RELATIONSHIPS,
            name=self.name,
        )

        feature_names: Set[str] = {f.name for f in blueprint.features}
        component_names: Set[str] = {c.name for c in blueprint.components}

        # --- Feature → component connection ------------------------------
        for unit in blueprint.features:
            if not unit.introduces_components:
                result.add_warning(
                    code="feature_no_components",
                    message=(
                        f"Feature '{unit.name}' does not introduce any "
                        f"components."
                    ),
                    affected=unit.name,
                    resolution_hint=(
                        f"Assign at least one component to '{unit.name}'."
                    ),
                )

            # Check that the components the feature introduces exist.
            for comp in unit.introduces_components:
                if comp not in component_names:
                    result.add_error(
                        code="feature_introduces_missing_component",
                        message=(
                            f"Feature '{unit.name}' introduces component "
                            f"'{comp}' which does not exist in the "
                            f"blueprint."
                        ),
                        affected=comp,
                        resolution_hint=(
                            f"Add the missing component '{comp}' or "
                            f"remove it from '{unit.name}'."
                        ),
                    )

        # --- Component → feature back-reference -------------------------
        for comp in blueprint.components:
            if comp.source_feature and comp.source_feature not in feature_names:
                result.add_warning(
                    code="component_source_feature_missing",
                    message=(
                        f"Component '{comp.name}' references source "
                        f"feature '{comp.source_feature}' which does "
                        f"not exist."
                    ),
                    affected=comp.name,
                    resolution_hint=(
                        "Update the source_feature reference or remove it."
                    ),
                )

        # --- Component relationships -------------------------------------
        seen_rels: Set[Tuple[str, str, str]] = set()
        for rel in blueprint.relationships:
            # Source must be a known component.
            if rel.source not in component_names:
                result.add_error(
                    code="relationship_source_missing",
                    message=(
                        f"Relationship source '{rel.source}' is not a "
                        f"known component."
                    ),
                    affected=rel.source,
                    resolution_hint="Remove the dangling relationship.",
                )
            # Target must be a known component.
            if rel.target not in component_names:
                result.add_error(
                    code="relationship_target_missing",
                    message=(
                        f"Relationship target '{rel.target}' is not a "
                        f"known component."
                    ),
                    affected=rel.target,
                    resolution_hint="Remove the dangling relationship.",
                )
            # Duplicate detection.
            key = (rel.source, rel.target, rel.kind)
            if key in seen_rels:
                result.add_warning(
                    code="duplicate_relationship",
                    message=(
                        f"Duplicate relationship: {rel.source} "
                        f"\u2192 {rel.target} ({rel.kind})."
                    ),
                    affected=rel.source,
                    resolution_hint="Remove the duplicate relationship.",
                )
            else:
                seen_rels.add(key)

        # --- Feature depends_on_features ---------------------------------
        for unit in blueprint.features:
            for dep in unit.depends_on_features:
                if dep not in feature_names:
                    result.add_error(
                        code="feature_depends_on_missing_feature",
                        message=(
                            f"Feature '{unit.name}' depends on feature "
                            f"'{dep}' which does not exist."
                        ),
                        affected=unit.name,
                        resolution_hint=(
                            f"Add the missing feature '{dep}' or remove "
                            f"the dependency."
                        ),
                    )

        # --- Component depends_on_components ----------------------------
        for comp in blueprint.components:
            for dep in comp.dependencies:
                if dep not in component_names:
                    result.add_error(
                        code="component_depends_on_missing_component",
                        message=(
                            f"Component '{comp.name}' depends on "
                            f"component '{dep}' which does not exist."
                        ),
                        affected=comp.name,
                        resolution_hint=(
                            f"Add the missing component '{dep}' or "
                            f"remove the dependency."
                        ),
                    )

        result.duration_ms = (time.perf_counter() - start) * 1000
        return result


__all__ = ["Layer3Relationships"]
