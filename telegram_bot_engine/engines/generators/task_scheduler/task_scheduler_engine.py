"""
TaskSchedulerEngine — Specification 063 (MAXIMUM CRITICAL)

Central task scheduler: registration, FIFO/priority/deadline/round-robin,
dependencies, delayed/periodic execution, retry, cancellation, windows
and load-aware scheduling.
"""

from __future__ import annotations

import hashlib
import logging

from ....core.context import GenerationContext
from ....core.result import StageResult
from ...base.base_engine import BaseEngine
from .data_readers import (
    QueueReader, ServiceReader, OrchestratorReader,
    ResourceReader, ExecutionContextReader, UserRequestReader,
)
from .report_data import (
    TaskSchedulerReport, ALL_SOURCES,
    SOURCE_QUEUE, SOURCE_SERVICE, SOURCE_ORCHESTRATOR,
    SOURCE_RESOURCE, SOURCE_EXECUTION_CONTEXT, SOURCE_USER_REQUEST,
)
from .scheduler import TaskScheduler
from .cache_manager import CacheManager
from .quality_gate import QualityGate
from .blueprint_builder import BlueprintBuilder

_log = logging.getLogger("engine.task_scheduler")


class TaskSchedulerEngine(BaseEngine):
    """Specification 063 — Intelligent Task Scheduler Engine."""

    def __init__(self) -> None:
        super().__init__(
            name="task_scheduler",
            version="1.0.0",
            description=(
                "Central task scheduler for the platform. Supports FIFO, priority, "
                "deadline and round-robin policies with dependency ordering, delayed "
                "and periodic tasks, retry scheduling, cancellation, execution "
                "windows and load-aware throttling."
            ),
            tags=[
                "scheduler", "tasks", "priority", "dependencies",
                "periodic", "retry", "load",
            ],
            metadata={"specification": "063", "priority": "MAXIMUM CRITICAL"},
        )
        self._queue_reader = QueueReader()
        self._svc_reader = ServiceReader()
        self._orch_reader = OrchestratorReader()
        self._res_reader = ResourceReader()
        self._ctx_reader = ExecutionContextReader()
        self._request_reader = UserRequestReader()
        self._scheduler = TaskScheduler()
        self._cache = CacheManager(enabled=True)
        self._quality_gate = QualityGate()
        self._builder = BlueprintBuilder()

    def execute(self, context: GenerationContext) -> StageResult:
        try:
            _log.info("TaskSchedulerEngine starting (Spec 063)")

            request_data = self._request_reader.read(context)
            queue_data = self._queue_reader.read(context)
            svc_data = self._svc_reader.read(context)
            orch_data = self._orch_reader.read(context)
            res_data = self._res_reader.read(context)
            ctx_data = self._ctx_reader.read(context)

            sources_used = []
            sources_missing = []
            for key, data in (
                (SOURCE_USER_REQUEST, request_data),
                (SOURCE_QUEUE, queue_data),
                (SOURCE_SERVICE, svc_data),
                (SOURCE_ORCHESTRATOR, orch_data),
                (SOURCE_RESOURCE, res_data),
                (SOURCE_EXECUTION_CONTEXT, ctx_data),
            ):
                if data.available:
                    sources_used.append(key)
                else:
                    sources_missing.append(key)

            cache_payload = str(sorted(sources_used)) + str(
                len(request_data.items or [])
                or (orch_data.raw or {}).get("task_count")
                or ""
            )
            cache_key = hashlib.sha256(cache_payload.encode("utf-8")).hexdigest()[:32]

            cached = self._cache.get(cache_key)
            if cached is not None:
                try:
                    report = TaskSchedulerReport(**{
                        k: v for k, v in cached.items()
                        if k in TaskSchedulerReport.__dataclass_fields__
                    })
                except Exception:
                    report = None
                if report is not None:
                    report.cache_info = self._cache.info_for_hit(cache_key)
                    context.set("task_scheduler_report", report)
                    return self.ok(
                        outputs={"task_scheduler_report": report.to_dict()},
                        metadata={"cache": "hit"},
                    )

            (
                tasks, events, retries, stats, policy,
                dep_viol, early_viol, throttled, mon_self_ok,
            ) = self._scheduler.schedule(
                queue_data, svc_data, orch_data, res_data, ctx_data, request_data,
            )

            self_ok = self._scheduler.self_verify(
                tasks, events, dep_viol, early_viol, mon_self_ok,
            )

            confidence = self._confidence(
                sources_used, sources_missing, tasks, events, self_ok,
            )

            report = self._builder.build(
                tasks=tasks,
                events=events,
                retries=retries,
                stats=stats,
                sources_used=sources_used,
                sources_missing=sources_missing,
                policy=policy,
                dependency_violations=dep_viol,
                early_start_violations=early_viol,
                load_throttled=throttled,
                self_verification_passed=self_ok,
                confidence=confidence,
            )

            gate_findings, passed, verdict = self._quality_gate.validate(report)
            report.findings.extend(gate_findings)
            report.verdict = verdict
            report.readiness_status = verdict
            report.self_verification_passed = self_ok

            report_dict = report.to_dict()
            report.cache_info = self._cache.put(cache_key, report_dict)
            context.set("task_scheduler_report", report)

            _log.info(
                "TaskSchedulerEngine finished — verdict=%s tasks=%d completed=%d",
                verdict, len(tasks), report.completed_count,
            )

            if not passed:
                return self.failed(
                    errors=[
                        f"Task Scheduler failed quality gate "
                        f"(verdict={verdict})"
                    ],
                    outputs={"task_scheduler_report": report_dict},
                    warnings=[f.message for f in gate_findings],
                )
            return self.ok(
                outputs={"task_scheduler_report": report_dict},
                metadata={
                    "report_id": report.report_id,
                    "verdict": verdict,
                    "task_count": len(tasks),
                    "completed_count": report.completed_count,
                    "failed_count": report.failed_count,
                    "cancelled_count": report.cancelled_count,
                    "dependency_violations": dep_viol,
                    "early_start_violations": early_viol,
                    "load_throttled": throttled,
                    "policy": policy,
                    "self_verification_passed": self_ok,
                    "confidence": confidence,
                },
            )
        except Exception as exc:
            _log.exception("TaskSchedulerEngine crashed: %s", exc)
            return self.failed(errors=[f"TaskSchedulerEngine error: {exc}"])

    def _confidence(self, used, missing, tasks, events, self_ok) -> float:
        total = len(ALL_SOURCES)
        ratio = len(used) / total if total else 0.0
        richness = min(1.0, len(tasks) / 5.0)
        activity = min(1.0, len(events) / max(1, len(tasks) * 2))
        penalty = 0.0 if self_ok else 0.25
        conf = (0.25 * ratio) + (0.25 * richness) + (0.30 * activity) + 0.20 - penalty
        return round(max(0.0, min(1.0, conf)), 3)


__all__ = ["TaskSchedulerEngine"]
