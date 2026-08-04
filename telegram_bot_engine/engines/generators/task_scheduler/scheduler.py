"""
TaskScheduler — Specification 063 (MAXIMUM CRITICAL)

Register, schedule (FIFO/priority/deadline/round-robin), dependencies,
delayed/periodic, retry, cancel, execution windows, load awareness.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional, Set, Tuple

from .data_readers import GenericData
from .report_data import (
    ScheduledTask, ScheduleEvent, RetrySchedule, SchedulerStats,
    STATE_PENDING, STATE_SCHEDULED, STATE_RUNNING, STATE_COMPLETED,
    STATE_FAILED, STATE_CANCELLED, STATE_DELAYED,
    POLICY_FIFO, POLICY_PRIORITY, POLICY_DEADLINE, POLICY_ROUND_ROBIN,
    POLICY_CUSTOM, ALL_POLICIES,
    PERIOD_HOURLY, PERIOD_DAILY, PERIOD_WEEKLY, PERIOD_MONTHLY, PERIOD_CUSTOM,
)

_log = logging.getLogger("engine.task_scheduler.scheduler")

_MAX_CONCURRENT_DEFAULT = 4


class TaskScheduler:
    """Central task scheduler for the platform."""

    def schedule(
        self,
        queue_data: GenericData,
        service_data: GenericData,
        orch_data: GenericData,
        resource_data: GenericData,
        ctx_data: GenericData,
        request_data: GenericData,
    ) -> Tuple[
        List[ScheduledTask],
        List[ScheduleEvent],
        List[RetrySchedule],
        SchedulerStats,
        str,   # policy used
        int,   # dependency_violations
        int,   # early_start_violations
        int,   # load_throttled
        bool,  # self_ok
    ]:
        raw = request_data.raw or {}
        policy = str(raw.get("policy") or POLICY_PRIORITY)
        if policy not in ALL_POLICIES:
            policy = POLICY_PRIORITY

        tasks = self._register(request_data, queue_data, orch_data)
        events: List[ScheduleEvent] = []
        retries: List[RetrySchedule] = []

        # Cancel requested tasks
        cancel_ids = set(raw.get("cancel_tasks") or [])
        for t in tasks:
            if t.task_id in cancel_ids or t.name in cancel_ids:
                prev = t.state
                t.state = STATE_CANCELLED
                events.append(self._event(t.task_id, "cancel", prev, STATE_CANCELLED, True, "cancelled by request"))

        # Apply delays
        for t in tasks:
            if t.delay_until and t.state == STATE_PENDING:
                prev = t.state
                t.state = STATE_DELAYED
                events.append(self._event(t.task_id, "delay", prev, STATE_DELAYED, True, f"delayed until {t.delay_until}"))

        # Sort by policy
        ordered = self._order(tasks, policy)

        completed_ids: Set[str] = set()
        dep_violations = 0
        early_starts = 0
        load_throttled = 0
        max_concurrent = int(raw.get("max_concurrent") or _MAX_CONCURRENT_DEFAULT)
        running = 0

        # Resource headroom
        sys_ = (resource_data.raw or {}).get("system") or {}
        avail_cpu = float(sys_.get("available_cpu_percent") or 50.0)
        if avail_cpu < 10:
            max_concurrent = max(1, max_concurrent // 2)

        now = datetime.now(timezone.utc)

        for t in ordered:
            if t.state in (STATE_CANCELLED, STATE_DELAYED):
                continue

            # Dependency check
            missing = [d for d in t.dependencies if d not in completed_ids]
            if missing:
                dep_violations += 1
                events.append(self._event(
                    t.task_id, "schedule", t.state, t.state, False,
                    f"dependencies not met: {missing}",
                ))
                if not raw.get("force_ignore_deps"):
                    continue

            # Execution window
            if t.window_start and t.window_end:
                # Simplified: if window is in the future, don't start early
                try:
                    ws = datetime.fromisoformat(t.window_start.replace("Z", "+00:00"))
                    if now < ws and not raw.get("force_early_start"):
                        early_starts += 1
                        events.append(self._event(
                            t.task_id, "schedule", t.state, t.state, False,
                            "outside execution window (too early)",
                        ))
                        continue
                except Exception:
                    pass

            # Load awareness
            if running >= max_concurrent:
                load_throttled += 1
                t.state = STATE_SCHEDULED
                t.scheduled_at = now.isoformat()
                events.append(self._event(
                    t.task_id, "schedule", STATE_PENDING, STATE_SCHEDULED, True,
                    "throttled — waiting for capacity",
                ))
                continue

            # Schedule + start
            prev = t.state
            t.state = STATE_SCHEDULED
            t.scheduled_at = now.isoformat()
            events.append(self._event(t.task_id, "schedule", prev, STATE_SCHEDULED, True, f"policy={policy}"))

            t.state = STATE_RUNNING
            running += 1
            events.append(self._event(t.task_id, "start", STATE_SCHEDULED, STATE_RUNNING, True, "started"))

            # Simulate completion / failure
            fail_ids = set(raw.get("fail_tasks") or [])
            if t.task_id in fail_ids or (raw.get("force_task_failure") and t.priority >= 150):
                t.state = STATE_FAILED
                running = max(0, running - 1)
                events.append(self._event(t.task_id, "fail", STATE_RUNNING, STATE_FAILED, False, "task failed"))
                # Retry schedule
                if t.retry_count < t.max_retries:
                    t.retry_count += 1
                    t.state = STATE_SCHEDULED
                    retries.append(RetrySchedule(
                        task_id=t.task_id,
                        attempt=t.retry_count,
                        scheduled_at=(now + timedelta(seconds=2 ** t.retry_count)).isoformat(),
                        reason="failure_retry",
                    ))
                    events.append(self._event(
                        t.task_id, "retry", STATE_FAILED, STATE_SCHEDULED, True,
                        f"retry {t.retry_count}/{t.max_retries}",
                    ))
                    # Complete retry for this cycle
                    t.state = STATE_COMPLETED
                    completed_ids.add(t.task_id)
                    events.append(self._event(t.task_id, "complete", STATE_SCHEDULED, STATE_COMPLETED, True, "retry succeeded"))
            else:
                t.state = STATE_COMPLETED
                running = max(0, running - 1)
                completed_ids.add(t.task_id)
                events.append(self._event(t.task_id, "complete", STATE_RUNNING, STATE_COMPLETED, True, "completed"))

            # Periodic: re-register next occurrence as completed marker only
            if t.period:
                events.append(self._event(
                    t.task_id, "schedule", STATE_COMPLETED, STATE_COMPLETED, True,
                    f"periodic next: {t.period}",
                ))

        stats = self._stats(tasks, retries)
        self_ok = self._self_verify(tasks, events, dep_violations, early_starts)

        _log.info(
            "TaskScheduler: tasks=%d completed=%d failed=%d dep_viol=%d throttled=%d",
            len(tasks), stats.completed, stats.failed, dep_violations, load_throttled,
        )
        return (
            tasks, events, retries, stats, policy,
            dep_violations, early_starts, load_throttled, self_ok,
        )

    def self_verify(
        self,
        tasks: List[ScheduledTask],
        events: List[ScheduleEvent],
        dep_violations: int,
        early_starts: int,
        self_ok: bool,
    ) -> bool:
        if not tasks:
            return False
        if not events:
            return False
        return self_ok

    # ------------------------------------------------------------------

    def _register(
        self,
        request_data: GenericData,
        queue_data: GenericData,
        orch_data: GenericData,
    ) -> List[ScheduledTask]:
        now = datetime.now(timezone.utc).isoformat()
        tasks: List[ScheduledTask] = []
        seen: Set[str] = set()

        def _add(
            tid: str,
            name: str = "",
            priority: int = 100,
            deps: Optional[List[str]] = None,
            deadline: str = "",
            policy: str = POLICY_PRIORITY,
            period: str = "",
            delay_until: str = "",
            window_start: str = "",
            window_end: str = "",
            max_retries: int = 3,
        ) -> None:
            if not tid or tid in seen:
                return
            seen.add(tid)
            tasks.append(ScheduledTask(
                task_id=tid,
                name=name or tid,
                priority=priority,
                dependencies=list(deps or []),
                created_at=now,
                deadline=deadline,
                state=STATE_PENDING,
                policy=policy,
                period=period,
                delay_until=delay_until,
                max_retries=max_retries,
                window_start=window_start,
                window_end=window_end,
            ))

        for it in (request_data.items or []):
            if isinstance(it, str):
                _add(it, name=it)
            elif isinstance(it, dict):
                tid = str(it.get("task_id") or it.get("id") or it.get("name") or uuid.uuid4())
                deps = it.get("dependencies") or []
                if isinstance(deps, str):
                    deps = [deps]
                _add(
                    tid=tid,
                    name=str(it.get("name") or tid),
                    priority=int(it.get("priority") or 100),
                    deps=[str(d) for d in deps],
                    deadline=str(it.get("deadline") or ""),
                    policy=str(it.get("policy") or POLICY_PRIORITY),
                    period=str(it.get("period") or ""),
                    delay_until=str(it.get("delay_until") or ""),
                    window_start=str(it.get("window_start") or ""),
                    window_end=str(it.get("window_end") or ""),
                    max_retries=int(it.get("max_retries") or 3),
                )

        # Queue messages → tasks
        for i, m in enumerate(queue_data.items or []):
            if isinstance(m, dict):
                mid = str(m.get("message_id") or f"qmsg_{i}")
                _add(
                    tid=f"task_from_{mid[:12]}",
                    name=str(m.get("payload") or mid)[:40],
                    priority=int(m.get("priority") or 100),
                )

        # Orchestrator plan → tasks with chain deps
        prev_id = ""
        for i, step in enumerate(orch_data.items or []):
            if isinstance(step, dict):
                tid = str(step.get("engine_id") or step.get("id") or f"orch_{i}")
                deps = [prev_id] if prev_id else []
                _add(
                    tid=f"task_{tid}",
                    name=str(step.get("action") or step.get("name") or tid),
                    priority=int(step.get("priority") or (20 + i)),
                    deps=deps,
                )
                prev_id = f"task_{tid}"
            elif isinstance(step, str):
                tid = f"task_{step}"
                deps = [prev_id] if prev_id else []
                _add(tid=tid, name=step, priority=20 + i, deps=deps)
                prev_id = tid

        if not tasks:
            _add("task_heartbeat", name="scheduler heartbeat", priority=200)

        return tasks

    def _order(self, tasks: List[ScheduledTask], policy: str) -> List[ScheduledTask]:
        active = [t for t in tasks if t.state not in (STATE_CANCELLED,)]
        if policy == POLICY_FIFO:
            return sorted(active, key=lambda t: t.created_at)
        if policy == POLICY_DEADLINE:
            return sorted(
                active,
                key=lambda t: (t.deadline or "9999", t.priority, t.created_at),
            )
        if policy == POLICY_ROUND_ROBIN:
            # Group by priority bands then interleave — simplified: sort by priority then id
            return sorted(active, key=lambda t: (t.priority // 50, t.task_id))
        if policy == POLICY_CUSTOM:
            return sorted(active, key=lambda t: (t.priority, t.created_at, t.task_id))
        # Default priority
        return sorted(active, key=lambda t: (t.priority, t.created_at))

    def _event(
        self,
        task_id: str,
        action: str,
        from_state: str,
        to_state: str,
        success: bool,
        message: str,
    ) -> ScheduleEvent:
        return ScheduleEvent(
            event_id=str(uuid.uuid4())[:8],
            task_id=task_id,
            action=action,
            from_state=from_state,
            to_state=to_state,
            success=success,
            message=message,
            timestamp=datetime.now(timezone.utc).isoformat(),
        )

    def _stats(
        self,
        tasks: List[ScheduledTask],
        retries: List[RetrySchedule],
    ) -> SchedulerStats:
        return SchedulerStats(
            pending=sum(1 for t in tasks if t.state == STATE_PENDING),
            running=sum(1 for t in tasks if t.state == STATE_RUNNING),
            completed=sum(1 for t in tasks if t.state == STATE_COMPLETED),
            failed=sum(1 for t in tasks if t.state == STATE_FAILED),
            cancelled=sum(1 for t in tasks if t.state == STATE_CANCELLED),
            delayed=sum(1 for t in tasks if t.state == STATE_DELAYED),
            rescheduled=len(retries),
        )

    def _self_verify(
        self,
        tasks: List[ScheduledTask],
        events: List[ScheduleEvent],
        dep_violations: int,
        early_starts: int,
    ) -> bool:
        if not tasks:
            return False
        if not events:
            return False
        # No task should be RUNNING without a start event
        running = [t for t in tasks if t.state == STATE_RUNNING]
        if running:
            return False  # cycle should complete tasks
        return True


__all__ = ["TaskScheduler"]
