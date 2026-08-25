"""
Dependency Graph Builder — builds the complete dependency graph with
relationships, priorities, version compatibility, and load order
(Specification 009).

The :class:`DependencyGraphBuilder` is a stateless helper that the
:class:`DependencyResolutionEngine` calls during the *graph building*
phase.  It takes the list of :class:`DependencyEntry` objects produced
by the :class:`LibraryDeterminer` and:

1. derives dependency-to-dependency relationships from the component
   dependency graph and the known library inter-dependencies,
2. records the reverse ``depended_by`` links on each dependency,
3. computes the load order (topological sort adjusted by priority),
4. produces a list of :class:`DependencyRelationship` objects and a
   list of :class:`DependencyOrderEntry` objects.

The builder does **not** create new dependencies.  It only wires the
existing dependencies together by recording their relationships and
computing the load order.

Data source
-----------
The builder reads **only**:

1. the list of :class:`DependencyEntry` objects (from the
   :class:`LibraryDeterminer`), and
2. the :class:`ComponentRegistry` (for the component dependency
   graph).

It does **not** read the user's request.
"""

from __future__ import annotations

from typing import Dict, List, Set, Tuple

from ..component_detector.registry import (
    ComponentRegistry,
    DetectedComponent,
)
from .report_data import (
    DEPENDENCY_PRIORITY_DATABASE,
    DEPENDENCY_PRIORITY_INFRASTRUCTURE,
    DependencyEntry,
    DependencyOrderEntry,
    DependencyRelationship,
)


# ---------------------------------------------------------------------------#
# Known library inter-dependencies
# ---------------------------------------------------------------------------#
#
# This table records which libraries depend on which other libraries.
# For example, alembic depends on SQLAlchemy, pytest-asyncio depends on
# pytest, and all database drivers are used by SQLAlchemy.

_KNOWN_INTER_DEPENDENCIES: Dict[str, List[str]] = {
    "alembic": ["SQLAlchemy"],
    "aiosqlite": ["SQLAlchemy"],
    "psycopg2": [],
    "psycopg2-binary": [],
    "redis": [],
    "pytest-asyncio": ["pytest"],
    "python-telegram-bot": [],
    "SQLAlchemy": [],
    "aiohttp": [],
    "httpx": [],
    "pydantic": [],
    "python-dotenv": [],
    "pytest": [],
    "black": [],
    "flake8": [],
    "mypy": [],
    "uvicorn": [],
    "mysqlclient": [],
}


class DependencyGraphBuilder:
    """Stateless helper that builds the dependency graph and load order.

    The builder is called by the
    :class:`DependencyResolutionEngine` after the
    :class:`LibraryDeterminer` has produced the list of dependency
    entries.  It wires the dependencies together by recording their
    relationships and computes the load order.

    The builder is **pure** with respect to the input list — it
    returns new lists of relationships and order entries.  It may
    update the ``depends_on`` and ``depended_by`` lists on the
    :class:`DependencyEntry` objects (these are the report's own data).
    """

    def build(
        self,
        dependencies: List[DependencyEntry],
        registry: ComponentRegistry,
    ) -> Tuple[List[DependencyRelationship], List[DependencyOrderEntry], List[str]]:
        """Build the dependency graph, relationships, and load order.

        Parameters:
            dependencies: The list of dependency entries.
            registry: The component registry (for the component
                dependency graph).

        Returns:
            A tuple ``(relationships, load_order, warnings)`` where:

            * ``relationships`` is the list of
              :class:`DependencyRelationship` objects.
            * ``load_order`` is the list of
              :class:`DependencyOrderEntry` objects.
            * ``warnings`` is a list of warning messages about
              dangling dependencies or unknown relationships.
        """
        warnings: List[str] = []

        # Build a name → dependency lookup.
        deps_by_name: Dict[str, DependencyEntry] = {
            d.name: d for d in dependencies
        }
        all_names: Set[str] = set(deps_by_name.keys())

        # -- Known inter-dependencies -------------------------------------#
        # Wire the known library-to-library dependencies (e.g. alembic
        # depends on SQLAlchemy).
        for dep in dependencies:
            inter_deps = _KNOWN_INTER_DEPENDENCIES.get(dep.name, [])
            for dep_name in inter_deps:
                if dep_name not in all_names:
                    warnings.append(
                        f"Dependency '{dep.name}' requires "
                        f"'{dep_name}' which is not in the dependency "
                        f"list."
                    )
                    continue
                if dep_name == dep.name:
                    continue
                dep.add_dependency(dep_name)
                deps_by_name[dep_name].add_dependent(dep.name)

        # -- Component-based dependencies --------------------------------#
        # If component A depends on component B, and A's libraries and
        # B's libraries are different, then A's libraries depend on
        # B's libraries.
        comp_by_name: Dict[str, DetectedComponent] = {
            c.name: c for c in registry.components
        }

        # Build a component → libraries lookup from the dependency
        # entries' source_components.
        comp_to_libs: Dict[str, List[str]] = {}
        for dep in dependencies:
            for comp_name in dep.source_components:
                comp_to_libs.setdefault(comp_name, []).append(dep.name)

        for dep in dependencies:
            for comp_name in dep.source_components:
                comp = comp_by_name.get(comp_name)
                if comp is None:
                    continue
                for dep_comp_name in comp.depends_on:
                    dep_comp_libs = comp_to_libs.get(dep_comp_name, [])
                    for dep_lib_name in dep_comp_libs:
                        if dep_lib_name == dep.name:
                            continue
                        if dep_lib_name not in all_names:
                            continue
                        if dep_lib_name not in dep.depends_on:
                            dep.add_dependency(dep_lib_name)
                        if dep.name not in deps_by_name[dep_lib_name].depended_by:
                            deps_by_name[dep_lib_name].add_dependent(dep.name)

        # Build the relationships list.
        relationships: List[DependencyRelationship] = []
        seen_rels: Set[Tuple[str, str, str]] = set()
        for dep in dependencies:
            for dep_name in dep.depends_on:
                key = (dep.name, dep_name, "depends_on")
                if key in seen_rels:
                    continue
                seen_rels.add(key)
                relationships.append(DependencyRelationship(
                    source=dep.name,
                    target=dep_name,
                    kind="depends_on",
                    description=(
                        f"Dependency '{dep.name}' depends on "
                        f"'{dep_name}'."
                    ),
                ))

        # Compute the load order.
        load_order = self._compute_load_order(dependencies)

        return relationships, load_order, warnings

    # -----------------------------------------------------------------#
    # Internal helpers
    # -----------------------------------------------------------------#

    def _compute_load_order(
        self,
        dependencies: List[DependencyEntry],
    ) -> List[DependencyOrderEntry]:
        """Compute the load order (topological sort by priority).

        The load order is a topological sort of the dependency graph,
        adjusted by dependency priority.  Dependencies with no
        dependencies come first; dependencies that depend on them come
        later.  When two dependencies have the same topological level,
        the one with the lower priority (higher importance) comes
        first, and ties are broken alphabetically by name.
        """
        if not dependencies:
            return []

        by_name: Dict[str, DependencyEntry] = {
            d.name: d for d in dependencies
        }
        all_names: Set[str] = set(by_name.keys())

        # Build the adjacency list (dependency → deps it depends on).
        deps: Dict[str, List[str]] = {}
        for d in dependencies:
            deps[d.name] = [
                x for x in d.depends_on if x in all_names
            ]

        # Compute the topological level for each node.
        levels: Dict[str, int] = {}

        def compute_level(
            name: str,
            visiting: Set[str],
        ) -> int:
            if name in levels:
                return levels[name]
            if name in visiting:
                return 0  # cycle guard
            visiting.add(name)
            dep_levels = [
                compute_level(x, visiting)
                for x in deps.get(name, [])
            ]
            visiting.discard(name)
            level = max(dep_levels) + 1 if dep_levels else 0
            levels[name] = level
            return level

        for name in all_names:
            compute_level(name, set())

        # Sort by (level, priority, name).
        sorted_deps = sorted(
            dependencies,
            key=lambda d: (
                levels.get(d.name, 0),
                d.priority,
                d.name,
            ),
        )

        # Assign load_order positions and build the entries.
        entries: List[DependencyOrderEntry] = []
        for position, d in enumerate(sorted_deps):
            d.load_order = position
            entries.append(DependencyOrderEntry(
                position=position,
                dependency_name=d.name,
                dependency_type=d.type,
                priority=d.priority,
                source_components=list(d.source_components),
            ))

        return entries


__all__ = ["DependencyGraphBuilder"]
