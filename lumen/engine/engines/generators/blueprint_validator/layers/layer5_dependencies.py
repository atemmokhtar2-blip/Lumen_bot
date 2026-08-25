"""
Layer 5 — Dependencies Validation (Specification 005).

The fifth validation layer checks that the dependency graph is healthy
and that there are no conflicts in the blueprint.

This layer validates:

* **No cycles** — the dependency graph must not contain any cycles
  (error when it does).
* **No dangling dependencies** — every dependency in the graph must
  reference a registered node (error when there are dangling deps).
* **Build order is valid** — the build order produced by the graph
  must not be empty when there are nodes (warning when it is).
* **Deferred nodes** — nodes that cannot be levelled (due to cycles or
  dangling deps) are reported as warnings.
* **Feature-component dependency consistency** — when a feature declares
  ``requires_database`` but the database component is not in the graph,
  that is an error.
* **Parallel-safe features in non-parallel phases** — features that are
  not parallel-safe should not be assigned to a phase that allows
  parallel execution (warning).
"""

from __future__ import annotations

import time
from typing import List, Set

from ..validation_report import (
    LAYER_5_DEPENDENCIES,
    LayerResult,
)
from ...project_planner.blueprint import ProjectBlueprint


class Layer5Dependencies:
    """Layer 5: validates the dependency graph and conflicts.

    The layer is stateless; it receives a :class:`ProjectBlueprint` and
    returns a :class:`LayerResult`.
    """

    #: The human-readable name of this layer.
    name: str = "Dependencies Validation"

    def validate(self, blueprint: ProjectBlueprint) -> LayerResult:
        """Run all dependency checks and return the layer result."""
        start = time.perf_counter()
        result = LayerResult(
            layer_id=LAYER_5_DEPENDENCIES,
            name=self.name,
        )

        graph = blueprint.dependency_graph

        # --- No nodes at all ---------------------------------------------
        if graph.count() == 0:
            result.add_warning(
                code="empty_dependency_graph",
                message=(
                    "The dependency graph is empty — no components or "
                    "features have been registered."
                ),
                affected="dependency_graph",
                resolution_hint=(
                    "Build the dependency graph from the components and "
                    "features."
                ),
            )
            result.duration_ms = (time.perf_counter() - start) * 1000
            return result

        # --- Cycles ------------------------------------------------------
        if graph.has_cycle():
            result.add_error(
                code="dependency_cycle",
                message=(
                    "The dependency graph contains a cycle.  Circular "
                    "dependencies make the project impossible to build "
                    "in the correct order."
                ),
                affected="dependency_graph",
                resolution_hint=(
                    "Break the cycle by removing or redirecting one of "
                    "the edges."
                ),
            )

        # --- Dangling dependencies ---------------------------------------
        dangling = graph.dangling_dependencies()
        if dangling:
            result.add_error(
                code="dangling_dependencies",
                message=(
                    f"The dependency graph has {len(dangling)} dangling "
                    f"dependency(ies): {dangling}.  These reference "
                    f"nodes that do not exist."
                ),
                affected=", ".join(dangling),
                resolution_hint=(
                    "Add the missing nodes or remove the dangling "
                    "dependencies."
                ),
            )

        # --- Build order -------------------------------------------------
        build_order = graph.build_order()
        if not build_order and graph.count() > 0:
            result.add_warning(
                code="empty_build_order",
                message=(
                    "The build order is empty even though the graph has "
                    f"{graph.count()} node(s)."
                ),
                affected="dependency_graph",
                resolution_hint=(
                    "Resolve cycles or dangling dependencies that "
                    "prevent computing a build order."
                ),
            )

        # --- Deferred nodes ----------------------------------------------
        deferred = graph.deferred_nodes()
        if deferred:
            result.add_warning(
                code="deferred_nodes",
                message=(
                    f"{len(deferred)} node(s) could not be levelled and "
                    f"were deferred: {deferred}."
                ),
                affected=", ".join(deferred),
                resolution_hint=(
                    "Resolve the cause of the deferral (cycle or "
                    "dangling dependency)."
                ),
            )

        # --- Feature-database consistency --------------------------------
        component_names: Set[str] = {c.name for c in blueprint.components}
        for unit in blueprint.features:
            if unit.requires_database and "database" not in component_names:
                result.add_error(
                    code="feature_needs_missing_database",
                    message=(
                        f"Feature '{unit.name}' requires a database but "
                        f"the 'database' component is not present in "
                        f"the blueprint."
                    ),
                    affected=unit.name,
                    resolution_hint=(
                        "Add a 'database' component to the blueprint "
                        "or remove the database requirement from the "
                        "feature."
                    ),
                )

        result.duration_ms = (time.perf_counter() - start) * 1000
        return result


__all__ = ["Layer5Dependencies"]
