"""
Plan Validator — validates the dependency resolution report
(Specification 009).

The :class:`PlanValidator` is a stateless helper that the
:class:`DependencyResolutionEngine` calls during the *validation*
phase.  It performs the final validation checks on the complete
:class:`DependencyResolutionReport`:

1. **All dependencies are complete.**  Every dependency entry must
   have a name, type, suggested version, reason, and source.
2. **No unresolved conflicts.**  No finding with severity ``"error"``
   and category ``"conflict"`` should remain.
3. **All relationships are valid.**  Every relationship's source and
   target must exist in the dependency list.
4. **The load order is valid.**  The load order must contain every
   dependency exactly once, in a topologically valid sequence.
5. **All components have dependencies.**  Every detected component in
   the component registry that requires libraries should be covered
   by at least one dependency.
6. **The report is not empty.**  The report must contain at least one
   dependency.
7. **Buildable.**  The dependency graph must be acyclic and the load
   order must be consistent with the dependency graph.

The validator does **not** modify the report — it only records
findings.

Data source
-----------
The validator reads the :class:`DependencyResolutionReport` and the
:class:`ComponentRegistry`.  It does **not** read the user's request.
"""

from __future__ import annotations

from typing import Dict, List, Set

from ..component_detector.registry import ComponentRegistry
from .report_data import (
    DependencyResolutionReport,
    DependencyRelationship,
    ResolutionFinding,
    SEVERITY_ERROR,
    SEVERITY_WARNING,
)


class PlanValidator:
    """Stateless helper that validates the dependency resolution report.

    The validator is called by the
    :class:`DependencyResolutionEngine` after all other helpers have
    run.  It performs the final validation checks on the complete
    report.
    """

    def validate(
        self,
        report: DependencyResolutionReport,
        registry: ComponentRegistry,
    ) -> List[ResolutionFinding]:
        """Validate the dependency resolution report.

        Parameters:
            report: The dependency resolution report to validate.
            registry: The component registry (for checking that all
                components have dependencies).

        Returns:
            A list of :class:`ResolutionFinding` objects describing
            all validation issues found.
        """
        findings: List[ResolutionFinding] = []

        findings.extend(self._check_not_empty(report))
        findings.extend(self._check_all_dependencies_complete(report))
        findings.extend(self._check_no_conflicts(report))
        findings.extend(self._check_all_relationships_valid(report))
        findings.extend(self._check_load_order_valid(report))
        findings.extend(self._check_all_components_have_dependencies(
            report, registry,
        ))
        findings.extend(self._check_buildable(report))

        return findings

    # -----------------------------------------------------------------#
    # Validation checks
    # -----------------------------------------------------------------#

    @staticmethod
    def _check_not_empty(
        report: DependencyResolutionReport,
    ) -> List[ResolutionFinding]:
        """Check that the report is not empty."""
        findings: List[ResolutionFinding] = []
        if report.is_empty:
            findings.append(ResolutionFinding(
                severity=SEVERITY_ERROR,
                code="empty_report",
                message=(
                    "The dependency resolution report is empty — "
                    "it contains no dependencies.  At least one "
                    "dependency must be resolved."
                ),
                affected="",
                resolution_hint=(
                    "Ensure the blueprint specifies a framework and "
                    "the component registry contains components."
                ),
                category="validation",
            ))
        return findings

    @staticmethod
    def _check_all_dependencies_complete(
        report: DependencyResolutionReport,
    ) -> List[ResolutionFinding]:
        """Check that every dependency entry is complete.

        Every dependency must have:
        * a non-empty name,
        * a non-empty type,
        * a non-empty suggested version,
        * a non-empty reason,
        * a non-empty source.
        """
        findings: List[ResolutionFinding] = []

        for dep in report.dependencies:
            if not dep.name:
                findings.append(ResolutionFinding(
                    severity=SEVERITY_ERROR,
                    code="dependency_without_name",
                    message=(
                        "A dependency entry has no name.  Every "
                        "dependency must have a name."
                    ),
                    affected="",
                    resolution_hint="Assign a name to the dependency.",
                    category="validation",
                ))

            if not dep.type:
                findings.append(ResolutionFinding(
                    severity=SEVERITY_ERROR,
                    code="dependency_without_type",
                    message=(
                        f"Dependency '{dep.name}' has no type.  "
                        f"Every dependency must have a type."
                    ),
                    affected=dep.name,
                    resolution_hint=(
                        f"Assign a type to '{dep.name}'."
                    ),
                    category="validation",
                ))

            if not dep.suggested_version:
                findings.append(ResolutionFinding(
                    severity=SEVERITY_ERROR,
                    code="dependency_without_version",
                    message=(
                        f"Dependency '{dep.name}' has no suggested "
                        f"version.  Every dependency must have a "
                        f"suggested version."
                    ),
                    affected=dep.name,
                    resolution_hint=(
                        f"Assign a suggested version to '{dep.name}'."
                    ),
                    category="validation",
                ))

            if not dep.reason:
                findings.append(ResolutionFinding(
                    severity=SEVERITY_ERROR,
                    code="dependency_without_reason",
                    message=(
                        f"Dependency '{dep.name}' has no reason.  "
                        f"Every dependency must record why it is "
                        f"needed."
                    ),
                    affected=dep.name,
                    resolution_hint=(
                        f"Add a reason for '{dep.name}'."
                    ),
                    category="validation",
                ))

            if not dep.source:
                findings.append(ResolutionFinding(
                    severity=SEVERITY_ERROR,
                    code="dependency_without_source",
                    message=(
                        f"Dependency '{dep.name}' has no source.  "
                        f"Every dependency must record where it was "
                        f"discovered."
                    ),
                    affected=dep.name,
                    resolution_hint=(
                        f"Set the source for '{dep.name}'."
                    ),
                    category="validation",
                ))

        return findings

    @staticmethod
    def _check_no_conflicts(
        report: DependencyResolutionReport,
    ) -> List[ResolutionFinding]:
        """Check that no unresolved conflicts remain.

        Any finding with severity ``"error"`` and category
        ``"conflict"`` is flagged here as a validation error.
        """
        findings: List[ResolutionFinding] = []

        conflict_errors = [
            f for f in report.findings
            if f.severity == SEVERITY_ERROR and f.category == "conflict"
        ]

        if conflict_errors:
            findings.append(ResolutionFinding(
                severity=SEVERITY_ERROR,
                code="unresolved_conflicts",
                message=(
                    f"The report contains {len(conflict_errors)} "
                    f"unresolved conflict(s).  All conflicts must "
                    f"be resolved before construction begins."
                ),
                affected=", ".join(
                    {f.affected for f in conflict_errors if f.affected}
                ),
                resolution_hint=(
                    "Resolve all conflict findings before proceeding."
                ),
                category="validation",
            ))

        return findings

    @staticmethod
    def _check_all_relationships_valid(
        report: DependencyResolutionReport,
    ) -> List[ResolutionFinding]:
        """Check that all relationship sources and targets exist."""
        findings: List[ResolutionFinding] = []

        all_names: Set[str] = {d.name for d in report.dependencies}

        for rel in report.relationships:
            if rel.source not in all_names:
                findings.append(ResolutionFinding(
                    severity=SEVERITY_ERROR,
                    code="invalid_relationship_source",
                    message=(
                        f"Relationship source '{rel.source}' does "
                        f"not exist in the dependency list."
                    ),
                    affected=rel.source,
                    resolution_hint=(
                        f"Remove the relationship or add a "
                        f"dependency named '{rel.source}'."
                    ),
                    category="validation",
                ))
            if rel.target not in all_names:
                findings.append(ResolutionFinding(
                    severity=SEVERITY_ERROR,
                    code="invalid_relationship_target",
                    message=(
                        f"Relationship target '{rel.target}' does "
                        f"not exist in the dependency list."
                    ),
                    affected=rel.target,
                    resolution_hint=(
                        f"Remove the relationship or add a "
                        f"dependency named '{rel.target}'."
                    ),
                    category="validation",
                ))

        return findings

    @staticmethod
    def _check_load_order_valid(
        report: DependencyResolutionReport,
    ) -> List[ResolutionFinding]:
        """Check that the load order is valid.

        The load order must:
        * contain every dependency exactly once,
        * be in topologically valid order (no dependency appears
          before a dependency it depends on).
        """
        findings: List[ResolutionFinding] = []

        all_names: Set[str] = {d.name for d in report.dependencies}
        order_names: List[str] = [
            o.dependency_name for o in report.load_order
        ]

        # Check that every dependency is in the order.
        for name in all_names:
            if name not in order_names:
                findings.append(ResolutionFinding(
                    severity=SEVERITY_ERROR,
                    code="dependency_not_in_order",
                    message=(
                        f"Dependency '{name}' is not in the load "
                        f"order."
                    ),
                    affected=name,
                    resolution_hint=(
                        f"Add '{name}' to the load order."
                    ),
                    category="validation",
                ))

        # Check for duplicates in the order.
        seen: Set[str] = set()
        for name in order_names:
            if name in seen:
                findings.append(ResolutionFinding(
                    severity=SEVERITY_ERROR,
                    code="duplicate_in_order",
                    message=(
                        f"Dependency '{name}' appears more than "
                        f"once in the load order."
                    ),
                    affected=name,
                    resolution_hint=(
                        f"Remove the duplicate entry for '{name}'."
                    ),
                    category="validation",
                ))
            seen.add(name)

        # Check topological validity — a dependency must not appear
        # before any dependency it depends on.
        position_by_name: Dict[str, int] = {
            o.dependency_name: o.position for o in report.load_order
        }

        for dep in report.dependencies:
            my_pos = position_by_name.get(dep.name, -1)
            if my_pos < 0:
                continue  # already flagged as not in order

            for dep_name in dep.depends_on:
                dep_pos = position_by_name.get(dep_name, -1)
                if dep_pos < 0:
                    continue  # dangling — already flagged
                if dep_pos > my_pos:
                    findings.append(ResolutionFinding(
                        severity=SEVERITY_ERROR,
                        code="invalid_load_order",
                        message=(
                            f"Dependency '{dep.name}' (position "
                            f"{my_pos}) appears before its "
                            f"dependency '{dep_name}' (position "
                            f"{dep_pos})."
                        ),
                        affected=dep.name,
                        resolution_hint=(
                            f"Move '{dep_name}' before '{dep.name}' "
                            f"in the load order."
                        ),
                        category="validation",
                    ))

        return findings

    @staticmethod
    def _check_all_components_have_dependencies(
        report: DependencyResolutionReport,
        registry: ComponentRegistry,
    ) -> List[ResolutionFinding]:
        """Check that components with required libraries are covered.

        For each component that declares ``required_libraries`` in its
        metadata, verify that at least one of those libraries appears
        in the dependency list.
        """
        findings: List[ResolutionFinding] = []

        all_dep_names_lower: Set[str] = {
            d.name.lower() for d in report.dependencies
        }

        for comp in registry.components:
            required_libs = comp.metadata.get("required_libraries", [])
            if not required_libs:
                continue

            covered = any(
                lib.lower() in all_dep_names_lower
                for lib in required_libs
            )

            if not covered:
                findings.append(ResolutionFinding(
                    severity=SEVERITY_WARNING,
                    code="component_without_dependencies",
                    message=(
                        f"Component '{comp.name}' declares "
                        f"required libraries "
                        f"{required_libs} but none appear in the "
                        f"dependency list."
                    ),
                    affected=comp.name,
                    resolution_hint=(
                        f"Add the required libraries for "
                        f"'{comp.name}' to the dependency list."
                    ),
                    category="validation",
                ))

        return findings

    @staticmethod
    def _check_buildable(
        report: DependencyResolutionReport,
    ) -> List[ResolutionFinding]:
        """Check that the dependency graph is buildable.

        The dependency graph is buildable if:
        * it is acyclic (already checked by the conflict detector,
          but we verify here),
        * the load order is consistent with the dependency graph.
        """
        findings: List[ResolutionFinding] = []

        # Verify acyclicity using a DFS-based cycle detection.
        adj: Dict[str, List[str]] = {}
        for dep in report.dependencies:
            adj[dep.name] = [
                d for d in dep.depends_on if d in adj or d in
                {x.name for x in report.dependencies}
            ]

        # Build adjacency list from all dependencies.
        all_names: Set[str] = {d.name for d in report.dependencies}
        adj = {name: [] for name in all_names}
        for dep in report.dependencies:
            for d in dep.depends_on:
                if d in all_names:
                    adj[dep.name].append(d)

        # DFS-based cycle detection.
        WHITE, GRAY, BLACK = 0, 1, 2
        color: Dict[str, int] = {name: WHITE for name in all_names}
        has_cycle = [False]

        def dfs(node: str) -> None:
            if has_cycle[0]:
                return
            color[node] = GRAY
            for neighbour in adj.get(node, []):
                if color[neighbour] == GRAY:
                    has_cycle[0] = True
                    return
                if color[neighbour] == WHITE:
                    dfs(neighbour)
            color[node] = BLACK

        for name in all_names:
            if color[name] == WHITE:
                dfs(name)
                if has_cycle[0]:
                    break

        if has_cycle[0]:
            findings.append(ResolutionFinding(
                severity=SEVERITY_ERROR,
                code="circular_dependencies",
                message=(
                    "The dependency graph contains circular "
                    "dependencies.  The project cannot be built "
                    "with circular dependencies."
                ),
                affected="",
                resolution_hint=(
                    "Break the circular dependency by removing or "
                    "redirecting one of the edges in the cycle."
                ),
                category="validation",
            ))

        return findings


__all__ = ["PlanValidator"]
