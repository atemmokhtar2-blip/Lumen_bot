"""
PlanBuilder — Specification 019

Assembles the final ExecutionPlan from the intermediate artefacts
produced by the specialised planners and analysers.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Dict, List, Optional

from .report_data import (
    ExecutionPlan,
    ExecutionPhase,
    ExecutionTask,
    TaskDependency,
    ParallelGroup,
    ExecutionConflict,
    ExecutionFinding,
    CacheInfo,
    ExecutionProvenance,
    PRIORITY_RANK,
    CONFIDENCE_HIGH,
    CONFIDENCE_MEDIUM,
    CONFIDENCE_LOW,
    CONFIDENCE_HIGH_THRESHOLD,
    CONFIDENCE_MEDIUM_THRESHOLD,
    VERDICT_NOT_READY,
)

_log = logging.getLogger("engine.execution_planning.plan_builder")


class PlanBuilder:
    """Builds the final ExecutionPlan object."""

    def build(
        self,
        phases: List[ExecutionPhase],
        dependencies: List[TaskDependency],
        parallel_groups: List[ParallelGroup],
        sequential_task_ids: List[str],
        conflicts: List[ExecutionConflict],
        findings: List[ExecutionFinding],
        sources_used: List[str],
        sources_missing: List[str],
        cache_info: Optional[CacheInfo] = None,
        confidence: float = 0.0,
    ) -> ExecutionPlan:
        """Assemble and return a complete ExecutionPlan."""

        # Flatten tasks
        tasks: List[ExecutionTask] = []
        for phase in phases:
            tasks.extend(phase.tasks)

        # Priority map
        priority_map: Dict[str, str] = {
            t.task_id: t.priority for t in tasks
        }

        # Global execution order (topological-ish + phase order + priority)
        execution_order = self._compute_execution_order(phases, dependencies)

        # Confidence level
        if confidence >= CONFIDENCE_HIGH_THRESHOLD:
            conf_level = CONFIDENCE_HIGH
        elif confidence >= CONFIDENCE_MEDIUM_THRESHOLD:
            conf_level = CONFIDENCE_MEDIUM
        else:
            conf_level = CONFIDENCE_LOW

        provenance = ExecutionProvenance(
            engine_name="execution_planning",
            engine_version="1.0.0",
            sources_used=list(sources_used),
            sources_missing=list(sources_missing),
            generated_at=datetime.now(timezone.utc).isoformat(),
            confidence=confidence,
            confidence_level=conf_level,
        )

        plan = ExecutionPlan(
            plan_id=str(uuid.uuid4()),
            phases=phases,
            tasks=tasks,
            dependencies=dependencies,
            parallel_groups=parallel_groups,
            sequential_task_ids=sequential_task_ids,
            conflicts=conflicts,
            findings=findings,
            execution_order=execution_order,
            priority_map=priority_map,
            readiness_status=VERDICT_NOT_READY,  # QualityGate will set the final value
            verdict=VERDICT_NOT_READY,
            cache_info=cache_info or CacheInfo(),
            provenance=provenance,
            is_empty=len(tasks) == 0,
        )

        _log.info(
            "PlanBuilder produced plan %s with %d phases, %d tasks, %d conflicts",
            plan.plan_id[:8],
            len(phases),
            len(tasks),
            len(conflicts),
        )
        return plan

    def _compute_execution_order(
        self,
        phases: List[ExecutionPhase],
        dependencies: List[TaskDependency],
    ) -> List[str]:
        """Produce a deterministic total order of task ids.

        Strategy:
        1. Sort phases by their numeric order.
        2. Inside each phase, respect hard dependencies (simple Kahn).
        3. Fall back to priority then task_id for ties.
        """
        from collections import defaultdict, deque

        order: List[str] = []
        hard_preds: Dict[str, set] = defaultdict(set)
        hard_succs: Dict[str, list] = defaultdict(list)

        for dep in dependencies:
            if dep.dependency_type == "hard":
                hard_preds[dep.to_task_id].add(dep.from_task_id)
                hard_succs[dep.from_task_id].append(dep.to_task_id)

        sorted_phases = sorted(phases, key=lambda p: p.order)

        for phase in sorted_phases:
            tasks = list(phase.tasks)
            # Kahn inside the phase
            in_degree = {
                t.task_id: len([
                    p for p in hard_preds.get(t.task_id, set())
                    if any(p == ot.task_id for ot in tasks)
                ])
                for t in tasks
            }
            # Secondary sort key: priority rank (higher first) then task_id
            def sort_key(tid: str) -> tuple:
                task = next((t for t in tasks if t.task_id == tid), None)
                pr = PRIORITY_RANK.get(task.priority, 0) if task else 0
                return (-pr, tid)

            queue = deque(
                sorted(
                    [tid for tid, deg in in_degree.items() if deg == 0],
                    key=sort_key,
                )
            )
            local_order: List[str] = []

            while queue:
                node = queue.popleft()
                local_order.append(node)
                for succ in hard_succs.get(node, []):
                    if succ in in_degree:
                        in_degree[succ] -= 1
                        if in_degree[succ] == 0:
                            # re-sort remaining ready nodes
                            ready = [tid for tid, deg in in_degree.items() if deg == 0 and tid not in local_order]
                            queue = deque(sorted(list(queue) + ready, key=sort_key))

            # Any remaining tasks (cycles or missing) are appended in priority order
            remaining = [t.task_id for t in tasks if t.task_id not in local_order]
            remaining.sort(key=sort_key)
            local_order.extend(remaining)

            order.extend(local_order)

        return order


__all__ = ["PlanBuilder"]
