"""
Risk Detection \u2014 analyses the plan before it is finalised
(Specification 004).

Before the Project Planning Engine adopts a plan, it runs a set of
risk-detection checks.  Each check returns zero or more
:class:`BlueprintRisk` objects.  The checks detect:

* **Conflicts** \u2014 contradictions carried over from the analysis
  report (e.g. two databases selected).
* **Missing pieces** \u2014 required information that was not supplied
  and has no default.
* **Missing phases** \u2014 execution phases that have no tasks and
  are not skippable.
* **Incomplete dependencies** \u2014 dependencies that reference
  non-existent components or that form a cycle.

The detector is a pure, stateless helper.  The planning engine calls
:meth:`RiskDetector.detect` with the assembled blueprint pieces and
receives the list of risks.  Risks with ``severity == "error"`` cause
the blueprint to be rejected (its :attr:`ready` flag stays ``False``).
"""

from __future__ import annotations

from typing import List

from .blueprint import BlueprintRisk, ProjectBlueprint
from .dependency_graph import DependencyGraph
from .execution_plan import ExecutionPlan
from .feature_unit import FeatureUnit


class RiskDetector:
    """Detects risks in a project plan before it is finalised.

    The detector is stateless; it receives the assembled pieces and
    returns a list of :class:`BlueprintRisk` objects.
    """

    def detect(
        self,
        *,
        conflicts: list,
        missing_info: list,
        feature_units: List[FeatureUnit],
        components: list,
        dependency_graph: DependencyGraph,
        execution_plan: ExecutionPlan,
    ) -> List[BlueprintRisk]:
        """Run all risk checks and return the combined risk list."""
        risks: List[BlueprintRisk] = []
        risks.extend(self._detect_conflicts(conflicts))
        risks.extend(self._detect_missing(missing_info))
        risks.extend(self._detect_missing_phases(execution_plan))
        risks.extend(self._detect_incomplete_dependencies(
            dependency_graph, components))
        risks.extend(self._detect_feature_isolation(feature_units))
        return risks

    # -- individual checks -------------------------------------------------

    def _detect_conflicts(self, conflicts: list) -> List[BlueprintRisk]:
        """Convert analysis conflicts into blueprint risks."""
        risks: List[BlueprintRisk] = []
        for conflict in conflicts:
            severity = getattr(conflict, "severity", "error")
            risks.append(BlueprintRisk(
                kind="conflict",
                description=getattr(conflict, "description",
                                    str(conflict)),
                severity=severity,
                affected=", ".join(getattr(conflict, "items", [])),
                resolution_hint=getattr(conflict, "resolution_hint", ""),
            ))
        return risks

    def _detect_missing(self, missing_info: list) -> List[BlueprintRisk]:
        """Convert missing-info entries into blueprint risks."""
        risks: List[BlueprintRisk] = []
        for info in missing_info:
            required = getattr(info, "required", True)
            if not required:
                continue  # optional missing info is only a warning
            field_name = getattr(info, "field", "unknown")
            question = getattr(info, "question", "")
            risks.append(BlueprintRisk(
                kind="missing",
                description=f"Missing required information: {field_name}. "
                            f"Question: {question}",
                severity="error",
                affected=field_name,
                resolution_hint="Ask the user and re-run the analyzer.",
            ))
        return risks

    def _detect_missing_phases(self,
                                plan: ExecutionPlan) -> List[BlueprintRisk]:
        """Detect phases that have no tasks and are not skippable."""
        risks: List[BlueprintRisk] = []
        for phase in plan.phases:
            if not phase.components and not phase.features \
                    and not phase.engines:
                if not phase.skippable:
                    risks.append(BlueprintRisk(
                        kind="missing_phase",
                        description=(
                            f"Phase {phase.number} ({phase.name}) has no "
                            "tasks assigned and is not skippable."
                        ),
                        severity="warning",
                        affected=phase.name,
                        resolution_hint=(
                            "Assign components to this phase or mark it "
                            "as skippable."
                        ),
                    ))
        return risks

    def _detect_incomplete_dependencies(
        self,
        graph: DependencyGraph,
        components: list,
    ) -> List[BlueprintRisk]:
        """Detect dangling dependencies and cycles."""
        risks: List[BlueprintRisk] = []
        component_names = {getattr(c, "name", str(c)) for c in components}

        dangling = graph.dangling_dependencies()
        for dep in dangling:
            risks.append(BlueprintRisk(
                kind="incomplete_dependency",
                description=(
                    f"Dependency '{dep}' references a component that does "
                    "not exist in the plan."
                ),
                severity="error",
                affected=dep,
                resolution_hint="Add the missing component or remove the "
                                "dependency.",
            ))

        if graph.has_cycle():
            risks.append(BlueprintRisk(
                kind="incomplete_dependency",
                description="A circular dependency was detected in the "
                            "component graph.",
                severity="error",
                affected=", ".join(graph.deferred_nodes()),
                resolution_hint="Break the cycle by removing or "
                                "reordering dependencies.",
            ))

        return risks

    def _detect_feature_isolation(
        self,
        feature_units: List[FeatureUnit],
    ) -> List[BlueprintRisk]:
        """Detect features that are completely isolated (no relationships).

        This is a warning, not an error \u2014 an isolated feature may
        be intentional, but it often signals a missing relationship.
        """
        risks: List[BlueprintRisk] = []
        all_referenced: set = set()
        for unit in feature_units:
            all_referenced.update(unit.depends_on_features)
            all_referenced.update(unit.depends_on_components)
        for unit in feature_units:
            if (unit.name not in all_referenced
                    and not unit.depends_on_features
                    and not unit.depends_on_components
                    and len(feature_units) > 1):
                risks.append(BlueprintRisk(
                    kind="missing",
                    description=(
                        f"Feature '{unit.name}' is not connected to any "
                        "other feature or component."
                    ),
                    severity="warning",
                    affected=unit.name,
                    resolution_hint="Review whether this feature should "
                                    "depend on or be depended on by others.",
                ))
        return risks


__all__ = ["RiskDetector"]
