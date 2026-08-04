"""
OrchestratorCore — Specification 053 (MAXIMUM CRITICAL)

Plans execution order, resolves dependencies, schedules parallel waves,
handles failures with retry, detects deadlocks, allocates resources,
and replans dynamically. No engine starts without going through this layer.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Dict, List, Set, Tuple

from .data_readers import GenericData
from .report_data import (
    PlannedTask, ExecutionRecord, ResourceAllocation, DeadlockInfo,
    PerformanceMetrics,
    MODE_SEQUENTIAL, MODE_PARALLEL,
    TASK_PENDING, TASK_WAITING, TASK_RUNNING, TASK_SUCCESS, TASK_FAILED,
    TASK_RETRYING, TASK_SKIPPED,
)

_log = logging.getLogger("engine.engine_orchestrator.orchestrator")


class OrchestratorCore:
    """Plan, schedule, monitor and replan engine execution."""

    def run(
        self,
        request_data: GenericData,
        ecosystem_data: GenericData,
        ctx_data: GenericData,
    ) -> Tuple[
        List[PlannedTask],
        List[ExecutionRecord],
        List[ResourceAllocation],
        List[DeadlockInfo],
        PerformanceMetrics,
        bool,  # replanned
    ]:
        engines = self._collect_engines(request_data, ecosystem_data)
        plan = self._build_plan(engines)
        deadlocks = self._detect_deadlocks(plan)
        if deadlocks:
            # Resolve by breaking cycles (drop lowest-priority edge logically)
            for d in deadlocks:
                d.resolved = True
                d.message += " (resolved by priority break)"
            plan = self._replan_after_deadlock(plan, deadlocks)
            replanned = True
        else:
            replanned = False

        # Assign parallel waves
        plan = self._assign_waves(plan)

        resources = self._allocate_resources(plan)
        history, metrics = self._simulate_execution(plan, request_data)

        # Failure-triggered replan
        if metrics.failure_count > 0 and (request_data.raw or {}).get("replan_on_failure", True):
            plan, history, metrics = self._replan_on_failure(plan, history, metrics, request_data)
            replanned = True

        _log.info(
            "OrchestratorCore: tasks=%d waves=%d failures=%d replanned=%s",
            len(plan), metrics.parallel_waves, metrics.failure_count, replanned,
        )
        return plan, history, resources, deadlocks, metrics, replanned

    def self_verify(
        self,
        plan: List[PlannedTask],
        history: List[ExecutionRecord],
        deadlocks: List[DeadlockInfo],
    ) -> bool:
        # Unresolved deadlocks block
        if any(not d.resolved for d in deadlocks):
            return False
        # Dependencies must be respected in success path
        success_ids = {
            h.engine_id for h in history if h.status == TASK_SUCCESS
        }
        task_by_engine = {t.engine_id: t for t in plan}
        for h in history:
            if h.status != TASK_SUCCESS:
                continue
            t = task_by_engine.get(h.engine_id)
            if not t:
                continue
            for dep in t.depends_on:
                if dep not in success_ids and dep in task_by_engine:
                    # dep planned but not successful — violation
                    dep_hist = [x for x in history if x.engine_id == dep]
                    if dep_hist and dep_hist[-1].status != TASK_SUCCESS:
                        return False
        return True

    def _collect_engines(
        self, request_data: GenericData, ecosystem_data: GenericData
    ) -> List[Dict]:
        engines: List[Dict] = []
        seen: Set[str] = set()

        # From ecosystem manifests
        for it in ecosystem_data.items or []:
            if not isinstance(it, dict):
                continue
            eid = str(it.get("engine_id") or it.get("id") or "")
            if not eid or eid in seen:
                continue
            # Skip orchestrator itself and isolated
            if eid == "engine_orchestrator":
                continue
            if str(it.get("status") or "").lower() == "isolated":
                continue
            seen.add(eid)
            engines.append({
                "engine_id": eid,
                "priority": int(it.get("priority") or 100),
                "dependencies": list(it.get("dependencies") or []),
            })

        # From request overrides
        for it in request_data.items or []:
            if isinstance(it, str):
                if it not in seen and it != "engine_orchestrator":
                    seen.add(it)
                    engines.append({"engine_id": it, "priority": 100, "dependencies": []})
            elif isinstance(it, dict):
                eid = str(it.get("engine_id") or it.get("id") or it.get("name") or "")
                if eid and eid not in seen and eid != "engine_orchestrator":
                    seen.add(eid)
                    engines.append({
                        "engine_id": eid,
                        "priority": int(it.get("priority") or 100),
                        "dependencies": list(it.get("dependencies") or []),
                    })

        # Fallback minimal set if empty
        if not engines:
            defaults = [
                ("intent_parser", 10, []),
                ("static_analysis", 125, []),
                ("unit_test_generation", 129, ["static_analysis"]),
                ("production_readiness", 131, ["unit_test_generation"]),
            ]
            for eid, pri, deps in defaults:
                engines.append({"engine_id": eid, "priority": pri, "dependencies": deps})

        engines.sort(key=lambda e: (e["priority"], e["engine_id"]))
        return engines

    def _build_plan(self, engines: List[Dict]) -> List[PlannedTask]:
        plan: List[PlannedTask] = []
        id_set = {e["engine_id"] for e in engines}
        for e in engines:
            deps = [d for d in e["dependencies"] if d in id_set]
            plan.append(PlannedTask(
                task_id=str(uuid.uuid4())[:8],
                engine_id=e["engine_id"],
                priority=e["priority"],
                mode=MODE_SEQUENTIAL,
                depends_on=deps,
                max_retries=2,
                status=TASK_PENDING,
                wave=0,
            ))
        return plan

    def _detect_deadlocks(self, plan: List[PlannedTask]) -> List[DeadlockInfo]:
        """Detect simple cycles in dependency graph."""
        graph: Dict[str, List[str]] = {t.engine_id: list(t.depends_on) for t in plan}
        deadlocks: List[DeadlockInfo] = []
        visited: Set[str] = set()
        stack: Set[str] = set()
        path: List[str] = []

        def dfs(node: str) -> bool:
            visited.add(node)
            stack.add(node)
            path.append(node)
            for nxt in graph.get(node, []):
                if nxt not in visited:
                    if dfs(nxt):
                        return True
                elif nxt in stack:
                    # cycle
                    cycle_start = path.index(nxt)
                    cycle = path[cycle_start:] + [nxt]
                    deadlocks.append(DeadlockInfo(
                        deadlock_id=str(uuid.uuid4())[:8],
                        engines=cycle,
                        message=f"Circular waiting: {' → '.join(cycle)}",
                        resolved=False,
                    ))
                    return True
            stack.discard(node)
            path.pop()
            return False

        for n in graph:
            if n not in visited:
                dfs(n)
        return deadlocks

    def _replan_after_deadlock(
        self, plan: List[PlannedTask], deadlocks: List[DeadlockInfo]
    ) -> List[PlannedTask]:
        """Break cycles by removing lowest-priority dependency edge."""
        priority = {t.engine_id: t.priority for t in plan}
        for d in deadlocks:
            if len(d.engines) < 2:
                continue
            # find edge from last unique to first in cycle with highest priority number (lowest urgency)
            nodes = [e for e in d.engines if e in priority]
            if len(nodes) < 2:
                continue
            # remove depends_on from the highest-priority-number engine toward cycle peer
            victim = max(nodes, key=lambda x: priority.get(x, 999))
            for t in plan:
                if t.engine_id == victim and t.depends_on:
                    t.depends_on = []
                    break
        return plan

    def _assign_waves(self, plan: List[PlannedTask]) -> List[PlannedTask]:
        """Kahn-like wave assignment for parallel groups."""
        remaining = {t.engine_id: set(t.depends_on) for t in plan}
        done: Set[str] = set()
        wave = 0
        task_map = {t.engine_id: t for t in plan}

        while remaining:
            ready = [eid for eid, deps in remaining.items() if deps <= done]
            if not ready:
                # force progress
                ready = [next(iter(remaining))]
            for eid in ready:
                t = task_map[eid]
                t.wave = wave
                t.mode = MODE_PARALLEL if len(ready) > 1 else MODE_SEQUENTIAL
                done.add(eid)
                del remaining[eid]
            wave += 1

        return plan

    def _allocate_resources(self, plan: List[PlannedTask]) -> List[ResourceAllocation]:
        n = max(1, len(plan))
        share = round(1.0 / n, 3)
        return [
            ResourceAllocation(
                engine_id=t.engine_id,
                cpu_share=share,
                ram_mb=round(256.0 / n, 1),
                threads=1,
            )
            for t in plan
        ]

    def _simulate_execution(
        self, plan: List[PlannedTask], request_data: GenericData
    ) -> Tuple[List[ExecutionRecord], PerformanceMetrics]:
        raw = request_data.raw or {}
        fail_set = set(raw.get("fail_engines") or [])
        history: List[ExecutionRecord] = []
        success = 0
        failure = 0
        retries = 0
        total_ms = 0.0
        ts = datetime.now(timezone.utc).isoformat()

        # Execute wave by wave
        max_wave = max((t.wave for t in plan), default=0)
        for t in sorted(plan, key=lambda x: (x.wave, x.priority)):
            attempt = 1
            status = TASK_SUCCESS
            error = ""
            duration = 10.0 + t.priority * 0.01

            if t.engine_id in fail_set or raw.get("force_fail") == t.engine_id:
                # retry policy
                while attempt <= t.max_retries:
                    retries += 1
                    attempt += 1
                status = TASK_FAILED
                error = f"Engine {t.engine_id} failed after {t.max_retries} retries"
                failure += 1
                t.status = TASK_FAILED
            else:
                success += 1
                t.status = TASK_SUCCESS

            total_ms += duration
            history.append(ExecutionRecord(
                record_id=str(uuid.uuid4())[:8],
                engine_id=t.engine_id,
                task_id=t.task_id,
                status=status,
                started_at=ts,
                finished_at=ts,
                duration_ms=duration,
                waiting_ms=float(t.wave * 2),
                attempt=attempt,
                error=error,
            ))

        metrics = PerformanceMetrics(
            total_tasks=len(plan),
            success_count=success,
            failure_count=failure,
            retry_count=retries,
            total_duration_ms=round(total_ms, 1),
            avg_duration_ms=round(total_ms / max(1, len(plan)), 1),
            success_rate=round(100.0 * success / max(1, len(plan)), 1),
            parallel_waves=max_wave + 1 if plan else 0,
        )
        return history, metrics

    def _replan_on_failure(
        self,
        plan: List[PlannedTask],
        history: List[ExecutionRecord],
        metrics: PerformanceMetrics,
        request_data: GenericData,
    ) -> Tuple[List[PlannedTask], List[ExecutionRecord], PerformanceMetrics]:
        """Skip dependents of failed engines; keep successful ones."""
        failed = {h.engine_id for h in history if h.status == TASK_FAILED}
        success = {h.engine_id for h in history if h.status == TASK_SUCCESS}

        for t in plan:
            if t.engine_id in failed:
                continue
            if any(d in failed for d in t.depends_on):
                t.status = TASK_SKIPPED
                history.append(ExecutionRecord(
                    record_id=str(uuid.uuid4())[:8],
                    engine_id=t.engine_id,
                    task_id=t.task_id,
                    status=TASK_SKIPPED,
                    error=f"Skipped due to failed dependency",
                    attempt=1,
                ))

        # recompute metrics
        success_n = sum(1 for h in history if h.status == TASK_SUCCESS)
        fail_n = sum(1 for h in history if h.status == TASK_FAILED)
        metrics.success_count = success_n
        metrics.failure_count = fail_n
        metrics.total_tasks = len(plan)
        metrics.success_rate = round(100.0 * success_n / max(1, len(plan)), 1)
        return plan, history, metrics


__all__ = ["OrchestratorCore"]
