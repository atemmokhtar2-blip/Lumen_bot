"""
ConflictDetector — Specification 019

Performs a final pass over the assembled plan looking for
ordering violations, phase-order problems and other structural
conflicts that the specialised analysers may have missed.
"""

from __future__ import annotations

import logging
from typing import List

from .report_data import (
    ExecutionPhase,
    ExecutionTask,
    TaskDependency,
    ParallelGroup,
    ExecutionConflict,
    CONFLICT_PHASE_ORDER,
    CONFLICT_TASK_ORDER,
    CONFLICT_PARALLEL_VIOLATION,
    CONFLICT_MISSING_PHASE,
    CONFLICT_DUPLICATE_TASK,
    SEVERITY_CRITICAL,
    SEVERITY_HIGH,
    SEVERITY_MEDIUM,
    ALL_PHASES,
    PHASE_ORDER,
)

_log = logging.getLogger("engine.execution_planning.conflict_detector")


class ConflictDetector:
    """Detects residual conflicts in the execution plan."""

    def __init__(self) -> None:
        self.conflicts: List[ExecutionConflict] = []

    def detect(
        self,
        phases: List[ExecutionPhase],
        dependencies: List[TaskDependency],
        parallel_groups: List[ParallelGroup],
    ) -> List[ExecutionConflict]:
        """Run all conflict checks and return the list of conflicts."""
        self.conflicts = []

        self._check_missing_phases(phases)
        self._check_phase_order(phases)
        self._check_duplicate_tasks(phases)
        self._check_parallel_violations(phases, dependencies, parallel_groups)
        self._check_task_order_consistency(phases, dependencies)

        _log.info("ConflictDetector found %d additional conflicts", len(self.conflicts))
        return self.conflicts

    def _check_missing_phases(self, phases: List[ExecutionPhase]) -> None:
        present = {p.phase_id for p in phases}
        for expected in ALL_PHASES:
            if expected not in present:
                self.conflicts.append(ExecutionConflict(
                    conflict_id=f"missing_phase_{expected}",
                    conflict_type=CONFLICT_MISSING_PHASE,
                    severity=SEVERITY_HIGH,
                    message=f"Required phase '{expected}' is missing from the plan.",
                    affected_phases=[expected],
                    resolution_hint="Ensure the PhasePlanner always emits all canonical phases.",
                ))

    def _check_phase_order(self, phases: List[ExecutionPhase]) -> None:
        sorted_phases = sorted(phases, key=lambda p: p.order)
        for i in range(1, len(sorted_phases)):
            prev = sorted_phases[i - 1]
            curr = sorted_phases[i]
            if curr.order < prev.order:
                self.conflicts.append(ExecutionConflict(
                    conflict_id=f"phase_order_{prev.phase_id}_{curr.phase_id}",
                    conflict_type=CONFLICT_PHASE_ORDER,
                    severity=SEVERITY_CRITICAL,
                    message=(
                        f"Phase '{curr.phase_id}' (order={curr.order}) appears "
                        f"before '{prev.phase_id}' (order={prev.order})."
                    ),
                    affected_phases=[prev.phase_id, curr.phase_id],
                    resolution_hint="Re-sort phases according to PHASE_ORDER.",
                ))

    def _check_duplicate_tasks(self, phases: List[ExecutionPhase]) -> None:
        seen = {}
        for phase in phases:
            for task in phase.tasks:
                if task.task_id in seen:
                    self.conflicts.append(ExecutionConflict(
                        conflict_id=f"dup_{task.task_id}",
                        conflict_type=CONFLICT_DUPLICATE_TASK,
                        severity=SEVERITY_HIGH,
                        message=f"Duplicate task_id '{task.task_id}' detected.",
                        affected_tasks=[task.task_id],
                        affected_phases=[seen[task.task_id], phase.phase_id],
                        resolution_hint="Ensure every task_id is unique across the whole plan.",
                    ))
                else:
                    seen[task.task_id] = phase.phase_id

    def _check_parallel_violations(
        self,
        phases: List[ExecutionPhase],
        dependencies: List[TaskDependency],
        parallel_groups: List[ParallelGroup],
    ) -> None:
        """A task that has a hard dependency on another task in the same
        parallel group is a violation.
        """
        hard_edges = {
            (d.from_task_id, d.to_task_id)
            for d in dependencies
            if d.dependency_type == "hard"
        }
        for group in parallel_groups:
            ids = set(group.task_ids)
            for a in ids:
                for b in ids:
                    if a != b and (a, b) in hard_edges:
                        self.conflicts.append(ExecutionConflict(
                            conflict_id=f"par_viol_{a}_{b}",
                            conflict_type=CONFLICT_PARALLEL_VIOLATION,
                            severity=SEVERITY_HIGH,
                            message=(
                                f"Tasks '{a}' and '{b}' are marked parallel "
                                f"but a hard dependency exists between them."
                            ),
                            affected_tasks=[a, b],
                            affected_phases=[group.phase],
                            resolution_hint=(
                                "Remove the parallel grouping or the conflicting "
                                "hard dependency."
                            ),
                        ))

    def _check_task_order_consistency(
        self,
        phases: List[ExecutionPhase],
        dependencies: List[TaskDependency],
    ) -> None:
        """Verify that a task never depends on a task that belongs to a
        later phase.
        """
        phase_of: dict[str, str] = {}
        order_of: dict[str, int] = {}
        for phase in phases:
            for task in phase.tasks:
                phase_of[task.task_id] = phase.phase_id
                order_of[task.task_id] = phase.order

        for dep in dependencies:
            if dep.dependency_type != "hard":
                continue
            from_order = order_of.get(dep.from_task_id)
            to_order = order_of.get(dep.to_task_id)
            if from_order is None or to_order is None:
                continue
            if from_order > to_order:
                self.conflicts.append(ExecutionConflict(
                    conflict_id=f"task_order_{dep.from_task_id}_{dep.to_task_id}",
                    conflict_type=CONFLICT_TASK_ORDER,
                    severity=SEVERITY_CRITICAL,
                    message=(
                        f"Task '{dep.to_task_id}' (phase order {to_order}) "
                        f"depends on '{dep.from_task_id}' which belongs to a "
                        f"later phase (order {from_order})."
                    ),
                    affected_tasks=[dep.from_task_id, dep.to_task_id],
                    resolution_hint=(
                        "Move the dependent task to a later phase or remove "
                        "the invalid cross-phase dependency."
                    ),
                ))


__all__ = ["ConflictDetector"]
