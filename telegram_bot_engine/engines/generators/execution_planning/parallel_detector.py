"""
ParallelDetector — Specification 019

Identifies groups of tasks that can safely execute in parallel
and marks the remaining tasks as sequential.
"""

from __future__ import annotations

import logging
from collections import defaultdict
from typing import Dict, List, Set

from .report_data import (
    ExecutionPhase,
    ExecutionTask,
    ParallelGroup,
    TaskDependency,
    EXECUTION_MODE_PARALLEL,
    EXECUTION_MODE_SEQUENTIAL,
)

_log = logging.getLogger("engine.execution_planning.parallel_detector")


class ParallelDetector:
    """Detects parallel-safe task groups inside each phase."""

    def __init__(self) -> None:
        self.parallel_groups: List[ParallelGroup] = []
        self.sequential_task_ids: List[str] = []

    def detect(
        self,
        phases: List[ExecutionPhase],
        dependencies: List[TaskDependency],
    ) -> tuple[List[ParallelGroup], List[str]]:
        """Analyse the plan and return parallel groups + sequential list.

        Returns:
            (parallel_groups, sequential_task_ids)
        """
        self.parallel_groups = []
        self.sequential_task_ids = []

        # Build a quick lookup of hard dependencies.
        hard_preds: Dict[str, Set[str]] = defaultdict(set)
        for dep in dependencies:
            if dep.dependency_type == "hard":
                hard_preds[dep.to_task_id].add(dep.from_task_id)

        group_counter = 0

        for phase in phases:
            # Tasks that have no mutual hard dependencies can potentially
            # run in parallel *within the same phase*.
            candidates = [t for t in phase.tasks if t.task_id]
            independent: List[str] = []
            sequential: List[str] = []

            for task in candidates:
                preds = hard_preds.get(task.task_id, set())
                # A task is independent if none of its hard predecessors
                # belong to the same phase.
                same_phase_preds = {
                    p for p in preds
                    if any(p == t.task_id for t in phase.tasks)
                }
                if not same_phase_preds:
                    independent.append(task.task_id)
                    task.execution_mode = EXECUTION_MODE_PARALLEL
                else:
                    sequential.append(task.task_id)
                    task.execution_mode = EXECUTION_MODE_SEQUENTIAL

            if len(independent) >= 2:
                group_counter += 1
                group = ParallelGroup(
                    group_id=f"pg_{phase.phase_id}_{group_counter}",
                    task_ids=independent,
                    phase=phase.phase_id,
                    reason=(
                        f"Tasks inside phase '{phase.name}' share no "
                        f"hard intra-phase dependencies."
                    ),
                )
                self.parallel_groups.append(group)

            self.sequential_task_ids.extend(sequential)

        # Any task not already classified as parallel becomes sequential.
        all_task_ids = {t.task_id for p in phases for t in p.tasks}
        parallel_ids = {tid for g in self.parallel_groups for tid in g.task_ids}
        for tid in all_task_ids:
            if tid not in parallel_ids and tid not in self.sequential_task_ids:
                self.sequential_task_ids.append(tid)

        _log.info(
            "ParallelDetector found %d parallel groups and %d sequential tasks",
            len(self.parallel_groups),
            len(self.sequential_task_ids),
        )
        return self.parallel_groups, self.sequential_task_ids


__all__ = ["ParallelDetector"]
