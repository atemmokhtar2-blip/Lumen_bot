"""
DependencyAnalyzer — Specification 019

Builds the complete task-dependency graph, detects circular
dependencies, and validates that every referenced dependency
actually exists.
"""

from __future__ import annotations

import logging
from collections import defaultdict, deque
from typing import Dict, List, Set, Tuple

from .report_data import (
    ExecutionPhase,
    ExecutionTask,
    TaskDependency,
    ExecutionConflict,
    CONFLICT_CIRCULAR_DEPENDENCY,
    CONFLICT_MISSING_DEPENDENCY,
    CONFLICT_ORPHAN_TASK,
    SEVERITY_CRITICAL,
    SEVERITY_HIGH,
    SEVERITY_MEDIUM,
)

_log = logging.getLogger("engine.execution_planning.dependency_analyzer")


class DependencyAnalyzer:
    """Analyses and validates the dependency graph of the plan."""

    def __init__(self) -> None:
        self.findings: List[ExecutionConflict] = []
        self.dependencies: List[TaskDependency] = []

    def analyze(
        self,
        phases: List[ExecutionPhase],
    ) -> Tuple[List[TaskDependency], List[ExecutionConflict]]:
        """Build the dependency list and detect problems.

        Returns:
            (dependencies, conflicts)
        """
        self.findings = []
        self.dependencies = []

        all_tasks: Dict[str, ExecutionTask] = {}
        for phase in phases:
            for task in phase.tasks:
                all_tasks[task.task_id] = task

        # ------------------------------------------------------------------ #
        # 1. Collect explicit dependencies declared on tasks
        # ------------------------------------------------------------------ #
        for task in all_tasks.values():
            for dep_id in task.depends_on:
                self.dependencies.append(TaskDependency(
                    from_task_id=dep_id,
                    to_task_id=task.task_id,
                    dependency_type="hard",
                    reason=f"Declared dependency of '{task.name}'",
                ))

        # ------------------------------------------------------------------ #
        # 2. Detect missing dependencies
        # ------------------------------------------------------------------ #
        known_ids = set(all_tasks.keys())
        for dep in self.dependencies:
            if dep.from_task_id not in known_ids:
                self.findings.append(ExecutionConflict(
                    conflict_id=f"missing_dep_{dep.from_task_id}_{dep.to_task_id}",
                    conflict_type=CONFLICT_MISSING_DEPENDENCY,
                    severity=SEVERITY_CRITICAL,
                    message=(
                        f"Task '{dep.to_task_id}' depends on unknown task "
                        f"'{dep.from_task_id}'."
                    ),
                    affected_tasks=[dep.to_task_id, dep.from_task_id],
                    resolution_hint=(
                        "Either create the missing task or remove the "
                        "invalid dependency reference."
                    ),
                ))

        # ------------------------------------------------------------------ #
        # 3. Detect circular dependencies (Kahn + DFS fallback)
        # ------------------------------------------------------------------ #
        cycles = self._detect_cycles(all_tasks)
        for cycle in cycles:
            cycle_str = " → ".join(cycle + [cycle[0]])
            self.findings.append(ExecutionConflict(
                conflict_id=f"cycle_{'_'.join(cycle[:3])}",
                conflict_type=CONFLICT_CIRCULAR_DEPENDENCY,
                severity=SEVERITY_CRITICAL,
                message=f"Circular dependency detected: {cycle_str}",
                affected_tasks=list(cycle),
                resolution_hint=(
                    "Break the cycle by removing or reordering one of "
                    "the dependency edges."
                ),
            ))

        # ------------------------------------------------------------------ #
        # 4. Detect orphan tasks (no phase assignment – defensive)
        # ------------------------------------------------------------------ #
        for task_id, task in all_tasks.items():
            if not task.phase:
                self.findings.append(ExecutionConflict(
                    conflict_id=f"orphan_{task_id}",
                    conflict_type=CONFLICT_ORPHAN_TASK,
                    severity=SEVERITY_HIGH,
                    message=f"Task '{task_id}' has no assigned phase.",
                    affected_tasks=[task_id],
                    resolution_hint="Assign the task to a valid execution phase.",
                ))

        _log.info(
            "DependencyAnalyzer found %d dependencies and %d conflicts",
            len(self.dependencies),
            len(self.findings),
        )
        return self.dependencies, self.findings

    def _detect_cycles(
        self,
        all_tasks: Dict[str, ExecutionTask],
    ) -> List[List[str]]:
        """Return a list of cycles (each cycle is a list of task_ids)."""
        graph: Dict[str, List[str]] = defaultdict(list)
        for task in all_tasks.values():
            for dep in task.depends_on:
                if dep in all_tasks:
                    graph[dep].append(task.task_id)

        cycles: List[List[str]] = []
        visited: Set[str] = set()
        stack: Set[str] = set()
        path: List[str] = []

        def dfs(node: str) -> None:
            if node in stack:
                # Found a cycle – extract it from the path.
                try:
                    idx = path.index(node)
                    cycles.append(path[idx:])
                except ValueError:
                    cycles.append([node])
                return
            if node in visited:
                return
            visited.add(node)
            stack.add(node)
            path.append(node)
            for neighbour in graph.get(node, []):
                dfs(neighbour)
            path.pop()
            stack.discard(node)

        for task_id in all_tasks:
            if task_id not in visited:
                dfs(task_id)

        return cycles


__all__ = ["DependencyAnalyzer"]
