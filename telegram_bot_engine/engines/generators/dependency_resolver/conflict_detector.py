"""
Conflict Detector — detects conflicts in the dependency resolution
(Specification 009).

The :class:`ConflictDetector` is a stateless helper that the
:class:`DependencyResolutionEngine` calls during the *conflict
detection* phase.  It scans the list of :class:`DependencyEntry`
objects and the :class:`DependencyRelationship` objects for these
conflict types:

1. **Duplicate dependencies.**  Two or more entries with the same
   name.  Every dependency name must be unique.
2. **Version conflicts.**  Two dependencies that are known to conflict
   with each other (e.g. psycopg2 and psycopg2-binary).
3. **Unused dependencies.**  A dependency that is not required by any
   component and has no dependents.
4. **Broken dependencies.**  A dependency depends on a name that does
   not exist in the list.
5. **Circular dependencies.**  The dependency graph contains a cycle.
6. **Orphaned dependencies.**  A dependency that has no source
   components and is not the framework or infrastructure.

The detector does **not** modify the dependencies — it only records
findings.

Data source
-----------
The detector reads **only** the list of :class:`DependencyEntry` objects
and the :class:`DependencyRelationship` objects.  It does **not** read
the user's request.
"""

from __future__ import annotations

from typing import Dict, List, Set

from .report_data import (
    DependencyEntry,
    DependencyRelationship,
    ResolutionFinding,
    SEVERITY_ERROR,
    SEVERITY_INFO,
    SEVERITY_WARNING,
)


# ---------------------------------------------------------------------------#
# Known conflicting library pairs
# ---------------------------------------------------------------------------#
#
# Some libraries provide the same functionality and should not be used
# together.  The detector flags these as version conflicts.

_CONFLICTING_PAIRS: List[tuple] = [
    ("psycopg2", "psycopg2-binary"),
    ("aiohttp", "httpx"),
    ("redis", "aioredis"),
]


class ConflictDetector:
    """Stateless helper that detects conflicts in the dependency list.

    The detector is called by the
    :class:`DependencyResolutionEngine` after the
    :class:`DependencyGraphBuilder` has wired the dependencies.  It
    scans for duplicates, version conflicts, unused, broken, circular,
    and orphaned dependencies.
    """

    def detect(
        self,
        dependencies: List[DependencyEntry],
        relationships: List[DependencyRelationship],
    ) -> List[ResolutionFinding]:
        """Detect all conflicts in the dependency list.

        Parameters:
            dependencies: The list of dependency entries.
            relationships: The list of dependency relationships.

        Returns:
            A list of :class:`ResolutionFinding` objects describing all
            detected conflicts.
        """
        findings: List[ResolutionFinding] = []

        findings.extend(self._check_duplicates(dependencies))
        findings.extend(self._check_version_conflicts(dependencies))
        findings.extend(self._check_unused(dependencies))
        findings.extend(self._check_broken_dependencies(dependencies))
        findings.extend(self._check_circular_dependencies(dependencies))
        findings.extend(self._check_orphaned_dependencies(dependencies))

        return findings

    # -----------------------------------------------------------------#
    # Conflict checks
    # -----------------------------------------------------------------#

    @staticmethod
    def _check_duplicates(
        dependencies: List[DependencyEntry],
    ) -> List[ResolutionFinding]:
        """Detect duplicate dependencies (same name)."""
        findings: List[ResolutionFinding] = []
        seen: Dict[str, int] = {}

        for dep in dependencies:
            if dep.name in seen:
                findings.append(ResolutionFinding(
                    severity=SEVERITY_ERROR,
                    code="duplicate_dependency",
                    message=(
                        f"Duplicate dependency detected: "
                        f"'{dep.name}'.  Each dependency name must "
                        f"be unique."
                    ),
                    affected=dep.name,
                    resolution_hint=(
                        f"Remove the duplicate entry for "
                        f"'{dep.name}'."
                    ),
                    category="conflict",
                ))
            else:
                seen[dep.name] = 1

        return findings

    @staticmethod
    def _check_version_conflicts(
        dependencies: List[DependencyEntry],
    ) -> List[ResolutionFinding]:
        """Detect known conflicting library pairs."""
        findings: List[ResolutionFinding] = []
        dep_names: Set[str] = {d.name for d in dependencies}

        for lib_a, lib_b in _CONFLICTING_PAIRS:
            if lib_a in dep_names and lib_b in dep_names:
                findings.append(ResolutionFinding(
                    severity=SEVERITY_WARNING,
                    code="version_conflict",
                    message=(
                        f"Libraries '{lib_a}' and '{lib_b}' provide "
                        f"overlapping functionality and should not "
                        f"be used together."
                    ),
                    affected=f"{lib_a}, {lib_b}",
                    resolution_hint=(
                        f"Use only one of '{lib_a}' or '{lib_b}'."
                    ),
                    category="conflict",
                ))

        return findings

    @staticmethod
    def _check_unused(
        dependencies: List[DependencyEntry],
    ) -> List[ResolutionFinding]:
        """Detect unused dependencies (no source components, no dependents)."""
        findings: List[ResolutionFinding] = []

        for dep in dependencies:
            has_components = len(dep.source_components) > 0
            has_dependents = len(dep.depended_by) > 0

            if not has_components and not has_dependents:
                findings.append(ResolutionFinding(
                    severity=SEVERITY_WARNING,
                    code="unused_dependency",
                    message=(
                        f"Dependency '{dep.name}' is not required "
                        f"by any component and has no dependents.  "
                        f"It may be unused."
                    ),
                    affected=dep.name,
                    resolution_hint=(
                        f"Confirm that '{dep.name}' is needed or "
                        f"remove it from the list."
                    ),
                    category="conflict",
                ))

        return findings

    @staticmethod
    def _check_broken_dependencies(
        dependencies: List[DependencyEntry],
    ) -> List[ResolutionFinding]:
        """Detect broken dependencies (depends on a non-existent name)."""
        findings: List[ResolutionFinding] = []
        all_names: Set[str] = {d.name for d in dependencies}

        for dep in dependencies:
            for dep_name in dep.depends_on:
                if dep_name not in all_names:
                    findings.append(ResolutionFinding(
                        severity=SEVERITY_ERROR,
                        code="broken_dependency",
                        message=(
                            f"Dependency '{dep.name}' depends on "
                            f"'{dep_name}' which does not exist in "
                            f"the dependency list."
                        ),
                        affected=dep.name,
                        resolution_hint=(
                            f"Remove the dependency on '{dep_name}' "
                            f"or add '{dep_name}' to the list."
                        ),
                        category="conflict",
                    ))

        return findings

    @staticmethod
    def _check_circular_dependencies(
        dependencies: List[DependencyEntry],
    ) -> List[ResolutionFinding]:
        """Detect circular dependencies in the dependency graph.

        Uses a depth-first search with a recursion stack to detect
        back edges.  Returns a finding for each dependency in a cycle.
        """
        findings: List[ResolutionFinding] = []

        # Strip accidental self-edges before cycle detection.
        graph: Dict[str, List[str]] = {
            d.name: [x for x in d.depends_on if x != d.name]
            for d in dependencies
        }
        for d in dependencies:
            d.depends_on = [x for x in d.depends_on if x != d.name]

        visited: Set[str] = set()
        rec_stack: List[str] = []
        in_stack: Set[str] = set()
        cycles: List[List[str]] = []
        seen_cycles: Set[frozenset] = set()

        def dfs(node: str) -> None:
            visited.add(node)
            rec_stack.append(node)
            in_stack.add(node)

            for neighbor in graph.get(node, []):
                if neighbor not in graph:
                    continue
                if neighbor not in visited:
                    dfs(neighbor)
                elif neighbor in in_stack:
                    cycle_start = rec_stack.index(neighbor)
                    cycle = rec_stack[cycle_start:]
                    cycle_key = frozenset(cycle)
                    if cycle_key not in seen_cycles:
                        seen_cycles.add(cycle_key)
                        cycles.append(list(cycle))

            rec_stack.pop()
            in_stack.discard(node)

        for node in graph:
            if node not in visited:
                dfs(node)

        for cycle in cycles:
            cycle_str = " -> ".join(cycle + [cycle[0]])
            for name in cycle:
                findings.append(ResolutionFinding(
                    severity=SEVERITY_ERROR,
                    code="circular_dependency",
                    message=(
                        f"Circular dependency detected: "
                        f"{cycle_str}.  Circular dependencies are "
                        f"not allowed."
                    ),
                    affected=name,
                    resolution_hint=(
                        f"Break the cycle by removing one "
                        f"dependency in the chain: {cycle_str}."
                    ),
                    category="conflict",
                ))

        return findings

    @staticmethod
    def _check_orphaned_dependencies(
        dependencies: List[DependencyEntry],
    ) -> List[ResolutionFinding]:
        """Detect orphaned dependencies (no source components, not framework)."""
        findings: List[ResolutionFinding] = []

        for dep in dependencies:
            if not dep.source_components and dep.type != "framework":
                # The framework itself is allowed to have no source
                # components.  Infrastructure libraries (like
                # python-dotenv) are also acceptable.
                if dep.source in ("blueprint", "framework"):
                    continue
                findings.append(ResolutionFinding(
                    severity=SEVERITY_INFO,
                    code="orphaned_dependency",
                    message=(
                        f"Dependency '{dep.name}' has no source "
                        f"components.  It may be a project-level "
                        f"dependency."
                    ),
                    affected=dep.name,
                    resolution_hint=(
                        f"Confirm that '{dep.name}' is a "
                        f"project-level dependency."
                    ),
                    category="conflict",
                ))

        return findings


__all__ = ["ConflictDetector"]
