"""
Blueprint Validation (Specification 004).

A :class:`ProjectBlueprint` is **not adopted** unless it passes three
checks:

1. **All features connected** \u2014 every feature in the plan is
   reachable from the dependency graph (no orphan features).
2. **All dependencies valid** \u2014 no dangling references and no
   cycles in the dependency graph.
3. **All execution phases complete** \u2014 every phase has at least one
   task and the phases are contiguous.

The validator is a pure, stateless helper.  The planning engine calls
:meth:`BlueprintValidator.validate` with the assembled blueprint and
receives a :class:`BlueprintValidation` verdict.

The validator does **not** fix problems \u2014 it only reports them.
The planning engine decides whether to adopt, fix, or reject the plan.
"""

from __future__ import annotations

from typing import List

from .blueprint import BlueprintValidation, ProjectBlueprint
from .dependency_graph import DependencyGraph
from .execution_plan import ExecutionPlan
from .feature_unit import FeatureUnit


class BlueprintValidator:
    """Validates a project blueprint before it is adopted.

    The validator is stateless and side-effect free.
    """

    def validate(
        self,
        *,
        feature_units: List[FeatureUnit],
        dependency_graph: DependencyGraph,
        execution_plan: ExecutionPlan,
        risks: list,
    ) -> BlueprintValidation:
        """Run all three checks and return the verdict.

        The blueprint is valid only when all three checks pass **and**
        there are no error-severity risks.
        """
        validation = BlueprintValidation()

        # Check 1: all features connected.
        validation.all_features_connected = self._check_features_connected(
            feature_units, dependency_graph)
        if not validation.all_features_connected:
            validation.errors.append(
                "Not all features are connected to the dependency graph."
            )

        # Check 2: all dependencies valid.
        validation.dependencies_valid = self._check_dependencies_valid(
            dependency_graph)
        if not validation.dependencies_valid:
            validation.errors.append(
                "Dependency graph has dangling references or a cycle."
            )

        # Check 3: all execution phases complete.
        validation.phases_complete = self._check_phases_complete(
            execution_plan)
        if not validation.phases_complete:
            validation.errors.append(
                "Execution plan is incomplete: some phases have no tasks "
                "or the phases are not contiguous."
            )

        # Collect warnings from risks.
        for risk in risks:
            if getattr(risk, "severity", "") == "warning":
                validation.warnings.append(
                    getattr(risk, "description", str(risk))
                )

        # Final verdict: all three checks pass and no error risks.
        has_error_risks = any(
            getattr(r, "severity", "") == "error" for r in risks
        )
        validation.valid = (
            validation.all_features_connected
            and validation.dependencies_valid
            and validation.phases_complete
            and not has_error_risks
        )

        return validation

    # -- individual checks -------------------------------------------------

    def _check_features_connected(
        self,
        feature_units: List[FeatureUnit],
        graph: DependencyGraph,
    ) -> bool:
        """Return ``True`` when every feature is in the dependency graph.

        A feature is "connected" when it appears as a node in the
        graph (either as a dependency or a dependent of something).
        When there is only one feature, it is trivially connected.
        """
        if not feature_units:
            return True
        if len(feature_units) == 1:
            return True
        graph_names = set(graph.names())
        for unit in feature_units:
            if unit.name not in graph_names:
                # The feature might be connected via its components.
                connected = any(
                    comp in graph_names
                    for comp in unit.introduces_components
                )
                if not connected:
                    return False
        return True

    def _check_dependencies_valid(self,
                                    graph: DependencyGraph) -> bool:
        """Return ``True`` when the graph has no dangling deps or cycles."""
        if graph.has_cycle():
            return False
        if graph.dangling_dependencies():
            return False
        return True

    def _check_phases_complete(self, plan: ExecutionPlan) -> bool:
        """Return ``True`` when the plan is complete and contiguous."""
        return plan.is_complete()


__all__ = ["BlueprintValidator"]
