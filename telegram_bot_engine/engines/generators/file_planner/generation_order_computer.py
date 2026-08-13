"""
Generation Order Computer — computes the generation order for planned
files (Specification 008).

The :class:`GenerationOrderComputer` is a stateless helper that the
:class:`FileGenerationPlanningEngine` calls during the *ordering*
phase.  It takes the final list of :class:`FilePlanEntry` objects and
computes the order in which the code generators should create them.

The generation order is a **topological sort** of the file dependency
graph, adjusted by generation priority.  Files with no dependencies
come first; files that depend on them come later.  When two files have
the same topological level, the one with the lower generation priority
(higher importance) comes first, and ties are broken alphabetically by
path.

The computer does **not** modify the files — it only computes the
``build_order`` field on each file and produces a list of
:class:`FileGenerationOrderEntry` objects.

Data source
-----------
The computer reads **only** the list of :class:`FilePlanEntry`
objects.  It does **not** read the user's request.
"""

from __future__ import annotations

from typing import Dict, List, Set

from .plan_data import FileGenerationOrderEntry, FilePlanEntry


class GenerationOrderComputer:
    """Stateless helper that computes the generation order for files.

    The computer is called by the
    :class:`FileGenerationPlanningEngine` after all dependencies have
    been resolved.  It computes a topological sort of the file
    dependency graph and assigns each file a ``build_order`` position.
    """

    def compute(
        self,
        files: List[FilePlanEntry],
    ) -> List[FileGenerationOrderEntry]:
        """Compute the generation order for the given files.

        Parameters:
            files: The list of planned file entries.  The
                ``build_order`` field of each file is updated
                in place.

        Returns:
            A list of :class:`FileGenerationOrderEntry` objects,
            ordered by generation position (0-based).
        """
        if not files:
            return []

        by_path: Dict[str, FilePlanEntry] = {
            f.path: f for f in files
        }
        all_paths: Set[str] = set(by_path.keys())

        # Build the adjacency list (file → files it depends on).
        # Only include dependencies that exist in the plan.
        deps: Dict[str, List[str]] = {}
        for f in files:
            deps[f.path] = [
                d for d in f.depends_on if d in all_paths
            ]

        # Compute the topological level for each node.
        # Level 0 = no dependencies.  Level N = max(dep levels) + 1.
        levels: Dict[str, int] = {}

        def compute_level(
            path: str,
            visiting: Set[str],
        ) -> int:
            if path in levels:
                return levels[path]
            if path in visiting:
                # Cycle — should not happen (conflict detector catches
                # it), but guard against infinite recursion.
                return 0
            visiting.add(path)
            dep_levels = [
                compute_level(d, visiting)
                for d in deps.get(path, [])
            ]
            visiting.discard(path)
            level = max(dep_levels) + 1 if dep_levels else 0
            levels[path] = level
            return level

        for path in all_paths:
            compute_level(path, set())

        # Sort by (level, generation_priority, path).
        # Lower level first, lower priority (higher importance) first,
        # then alphabetically by path.
        sorted_files = sorted(
            files,
            key=lambda f: (
                levels.get(f.path, 0),
                f.generation_priority,
                f.path,
            ),
        )

        # Assign build_order positions and build the entries.
        entries: List[FileGenerationOrderEntry] = []
        for position, f in enumerate(sorted_files):
            f.build_order = position
            entries.append(FileGenerationOrderEntry(
                position=position,
                file_path=f.path,
                file_name=f.name,
                responsible_engine=f.responsible_engine,
                source_component=f.source_component,
            ))

        return entries


__all__ = ["GenerationOrderComputer"]
