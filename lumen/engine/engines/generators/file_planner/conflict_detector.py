"""
Conflict Detector — detects conflicts in the file generation plan
(Specification 008).

The :class:`ConflictDetector` is a stateless helper that the
:class:`FileGenerationPlanningEngine` calls during the *conflict
detection* phase.  It scans the list of :class:`FilePlanEntry` objects
and the :class:`FileGenerationPlan` for these conflict types:

1. **Duplicate files.**  Two or more files with the same path.
   Every file path must be unique in the plan.
2. **Naming conflicts.**  Two or more files in the same folder with
   the same name but different paths (e.g. case-insensitive
   collisions that could cause issues on case-insensitive file
   systems).
3. **Useless files.**  A file with no purpose, no reason for
   existence, or no source component.  Every file must have a clear
   reason to exist.
4. **Unlinked files.**  A file that has no dependencies and no
   dependents — it is not connected to any other file in the plan's
   dependency graph.  An unlinked file is a warning (not all files
   need to be linked, but it may indicate an oversight).
5. **Dangling dependencies.**  A file depends on a path that does not
   exist in the plan.
6. **Circular dependencies.**  The file dependency graph contains a
   cycle.

The detector does **not** modify the files or the plan — it only
records findings.

Data source
-----------
The detector reads **only** the list of :class:`FilePlanEntry` objects
and the :class:`FileGenerationPlan` relationships.  It does **not**
read the user's request.
"""

from __future__ import annotations

from typing import Dict, List, Set

from .plan_data import (
    FilePlanEntry,
    FileRelationship,
    PlanFinding,
    SEVERITY_ERROR,
    SEVERITY_WARNING,
)


class ConflictDetector:
    """Stateless helper that detects conflicts in the file plan.

    The detector is called by the
    :class:`FileGenerationPlanningEngine` after the
    :class:`FileDeterminer` has produced the list of planned files
    and the :class:`RelationshipResolver` has resolved their
    dependencies.  It scans for duplicates, naming conflicts, useless
    files, unlinked files, dangling dependencies, and circular
    dependencies.
    """

    def detect(
        self,
        files: List[FilePlanEntry],
        relationships: List[FileRelationship],
    ) -> List[PlanFinding]:
        """Detect all conflicts in the file plan.

        Parameters:
            files: The list of planned file entries.
            relationships: The list of file relationships.

        Returns:
            A list of :class:`PlanFinding` objects describing all
            detected conflicts.
        """
        findings: List[PlanFinding] = []

        findings.extend(self._check_duplicates(files))
        findings.extend(self._check_naming_conflicts(files))
        findings.extend(self._check_useless_files(files))
        findings.extend(self._check_unlinked_files(files))
        findings.extend(self._check_dangling_dependencies(files))
        findings.extend(self._check_circular_dependencies(files))

        return findings

    # -----------------------------------------------------------------#
    # Conflict checks
    # -----------------------------------------------------------------#

    @staticmethod
    def _check_duplicates(
        files: List[FilePlanEntry],
    ) -> List[PlanFinding]:
        """Detect duplicate files (same path)."""
        findings: List[PlanFinding] = []
        seen: Dict[str, int] = {}

        for f in files:
            path_key = f.path.lower()
            if path_key in seen:
                findings.append(PlanFinding(
                    severity=SEVERITY_ERROR,
                    code="duplicate_file",
                    message=(
                        f"Duplicate file path detected: '{f.path}'. "
                        f"Each file path must be unique in the plan."
                    ),
                    affected=f.path,
                    resolution_hint=(
                        f"Remove or rename the duplicate file at "
                        f"'{f.path}'."
                    ),
                ))
            else:
                seen[path_key] = 1

        return findings

    @staticmethod
    def _check_naming_conflicts(
        files: List[FilePlanEntry],
    ) -> List[PlanFinding]:
        """Detect naming conflicts (same name in the same folder, case-insensitive)."""
        findings: List[PlanFinding] = []

        # Group by (folder, name_lower).
        grouped: Dict[str, List[FilePlanEntry]] = {}
        for f in files:
            folder = f.folder or ""
            key = f"{folder}/{f.name.lower()}"
            grouped.setdefault(key, []).append(f)

        for key, group in grouped.items():
            if len(group) > 1:
                paths = ", ".join(f"'{f.path}'" for f in group)
                findings.append(PlanFinding(
                    severity=SEVERITY_WARNING,
                    code="naming_conflict",
                    message=(
                        f"Naming conflict: {len(group)} files in "
                        f"folder '{group[0].folder or ''}' have "
                        f"the same name '{group[0].name}' "
                        f"(case-insensitive): {paths}."
                    ),
                    affected=group[0].folder or group[0].path,
                    resolution_hint=(
                        f"Rename one of the conflicting files to "
                        f"avoid issues on case-insensitive file "
                        f"systems."
                    ),
                ))

        return findings

    @staticmethod
    def _check_useless_files(
        files: List[FilePlanEntry],
    ) -> List[PlanFinding]:
        """Detect useless files (no purpose, no reason, or no component)."""
        findings: List[PlanFinding] = []

        for f in files:
            if not f.purpose and not f.reason_for_existence:
                findings.append(PlanFinding(
                    severity=SEVERITY_ERROR,
                    code="file_without_purpose",
                    message=(
                        f"File '{f.path}' has no purpose and no "
                        f"reason for existence.  Every file must have "
                        f"a clear purpose."
                    ),
                    affected=f.path,
                    resolution_hint=(
                        f"Assign a purpose to '{f.name}' or remove "
                        f"it from the plan."
                    ),
                ))
            elif not f.source_component:
                findings.append(PlanFinding(
                    severity=SEVERITY_WARNING,
                    code="file_without_component",
                    message=(
                        f"File '{f.path}' has no source component. "
                        f"Every file should be linked to a detected "
                        f"component."
                    ),
                    affected=f.path,
                    resolution_hint=(
                        f"Link '{f.name}' to a component or confirm "
                        f"it is a project-level file."
                    ),
                ))

        return findings

    @staticmethod
    def _check_unlinked_files(
        files: List[FilePlanEntry],
    ) -> List[PlanFinding]:
        """Detect unlinked files (no dependencies and no dependents)."""
        findings: List[PlanFinding] = []

        for f in files:
            has_deps = len(f.depends_on) > 0
            has_dependents = len(f.depended_by) > 0

            if not has_deps and not has_dependents:
                findings.append(PlanFinding(
                    severity=SEVERITY_WARNING,
                    code="unlinked_file",
                    message=(
                        f"File '{f.path}' is unlinked — it has no "
                        f"dependencies and no dependents.  It is "
                        f"not connected to any other file in the "
                        f"plan's dependency graph."
                    ),
                    affected=f.path,
                    resolution_hint=(
                        f"Connect '{f.name}' to the project by "
                        f"adding a dependency or a dependent, or "
                        f"confirm it is a standalone file."
                    ),
                ))

        return findings

    @staticmethod
    def _check_dangling_dependencies(
        files: List[FilePlanEntry],
    ) -> List[PlanFinding]:
        """Detect dangling dependencies (depends on a non-existent path)."""
        findings: List[PlanFinding] = []

        all_paths: Set[str] = {f.path for f in files}

        for f in files:
            for dep in f.depends_on:
                if dep not in all_paths:
                    findings.append(PlanFinding(
                        severity=SEVERITY_ERROR,
                        code="dangling_dependency",
                        message=(
                            f"File '{f.path}' depends on '{dep}' "
                            f"which does not exist in the plan."
                        ),
                        affected=f.path,
                        resolution_hint=(
                            f"Remove the dependency on '{dep}' or "
                            f"add a file at path '{dep}'."
                        ),
                    ))

        return findings

    @staticmethod
    def _check_circular_dependencies(
        files: List[FilePlanEntry],
    ) -> List[PlanFinding]:
        """Detect circular dependencies in the file graph.

        Uses a depth-first search with a recursion stack to detect
        back edges.  Returns a finding for each file in a cycle.
        """
        findings: List[PlanFinding] = []

        graph: Dict[str, List[str]] = {
            f.path: list(f.depends_on) for f in files
        }

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
                    continue  # dangling — handled separately
                if neighbor not in visited:
                    dfs(neighbor)
                elif neighbor in in_stack:
                    # Found a cycle — extract it from the rec stack.
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
            for path in cycle:
                findings.append(PlanFinding(
                    severity=SEVERITY_ERROR,
                    code="circular_dependency",
                    message=(
                        f"Circular dependency detected: {cycle_str}. "
                        f"Circular dependencies are not allowed."
                    ),
                    affected=path,
                    resolution_hint=(
                        f"Break the cycle by removing one "
                        f"dependency in the chain: {cycle_str}."
                    ),
                ))

        return findings


__all__ = ["ConflictDetector"]
