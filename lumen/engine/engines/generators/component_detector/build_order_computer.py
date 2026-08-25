"""
Build Order Computer — computes the build order for detected components
(Specification 007).

The :class:`BuildOrderComputer` is a stateless helper that the
:class:`ComponentDetectionEngine` calls during the *ordering* phase.
It takes the final list of :class:`DetectedComponent` objects and
computes the order in which the code generators should build them.

The build order is a **topological sort** of the dependency graph,
adjusted by importance level.  Components with no dependencies come
first; components that depend on them come later.  When two components
have the same topological level, the one with higher importance
(critical before high before normal before low) comes first.

The computer does **not** modify the components — it only computes the
``build_order`` field on each component and produces a list of
:class:`ComponentBuildOrderEntry` objects.
"""

from __future__ import annotations

from typing import Dict, List, Set

from .registry import (
    ComponentBuildOrderEntry,
    DetectedComponent,
)


class BuildOrderComputer:
    """Stateless helper that computes the build order for components.

    The computer is called by the
    :class:`ComponentDetectionEngine` after all validation has
    passed.  It computes a topological sort of the dependency graph
    and assigns each component a ``build_order`` position.
    """

    def compute(
        self,
        components: List[DetectedComponent],
    ) -> List[ComponentBuildOrderEntry]:
        """Compute the build order for the given components.

        Parameters:
            components: The list of detected components.  The
                ``build_order`` field of each component is updated
                in place.

        Returns:
            A list of :class:`ComponentBuildOrderEntry` objects,
            ordered by build position (0-based).
        """
        if not components:
            return []

        by_name: Dict[str, DetectedComponent] = {
            c.name: c for c in components
        }
        all_names: Set[str] = set(by_name.keys())

        # Build the adjacency list (component → components it depends on).
        deps: Dict[str, List[str]] = {}
        for comp in components:
            deps[comp.name] = [
                d for d in comp.depends_on if d in all_names
            ]

        # Kahn's algorithm for topological sort, with importance-based
        # tie-breaking.
        in_degree: Dict[str, int] = {name: 0 for name in all_names}
        for name, dep_list in deps.items():
            for dep in dep_list:
                in_degree[name] = in_degree.get(name, 0) + 1

        # Reverse adjacency: for each dep, who depends on it?
        dependents: Dict[str, List[str]] = {
            name: [] for name in all_names
        }
        for name, dep_list in deps.items():
            for dep in dep_list:
                dependents[dep].append(name)

        # Compute the topological level for each node.
        # Level 0 = no dependencies.  Level N = max(dep levels) + 1.
        levels: Dict[str, int] = {}
        resolved: Set[str] = set()

        def compute_level(name: str, visiting: Set[str]) -> int:
            if name in levels:
                return levels[name]
            if name in visiting:
                # Cycle — should not happen (quality validator catches it).
                return 0
            visiting.add(name)
            dep_levels = [compute_level(d, visiting) for d in deps.get(name, [])]
            visiting.discard(name)
            level = max(dep_levels) + 1 if dep_levels else 0
            levels[name] = level
            resolved.add(name)
            return level

        for name in all_names:
            compute_level(name, set())

        # Sort by (level, importance_weight, name).
        sorted_components = sorted(
            components,
            key=lambda c: (levels.get(c.name, 0), c.importance_weight, c.name),
        )

        # Assign build_order positions and build the entries.
        entries: List[ComponentBuildOrderEntry] = []
        for position, comp in enumerate(sorted_components):
            comp.build_order = position
            entries.append(ComponentBuildOrderEntry(
                position=position,
                component_name=comp.name,
                component_type=comp.type,
                building_engine=comp.building_engine,
            ))

        return entries


__all__ = ["BuildOrderComputer"]
