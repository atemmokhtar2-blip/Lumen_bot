"""
WorkflowExecutionEngine — Specification 064 (MAXIMUM CRITICAL)

Execute workflows from execution plans: sequential/parallel/conditional
stages, branches, checkpoints, resume and rollback support.
"""

from __future__ import annotations

import hashlib
import logging

from ....core.context import GenerationContext
from ....core.result import StageResult
from ...base.base_engine import BaseEngine
from .data_readers import (
    SchedulerReader, QueueReader, OrchestratorReader,
    ExecutionContextReader, ServiceReader, UserRequestReader,
)
from .report_data import (
    WorkflowExecutionReport, ALL_SOURCES,
    SOURCE_SCHEDULER, SOURCE_QUEUE, SOURCE_ORCHESTRATOR,
    SOURCE_EXECUTION_CONTEXT, SOURCE_SERVICE, SOURCE_USER_REQUEST,
)
from .workflow_engine import WorkflowRunner
from .cache_manager import CacheManager
from .quality_gate import QualityGate
from .blueprint_builder import BlueprintBuilder

_log = logging.getLogger("engine.workflow_execution")


class WorkflowExecutionEngine(BaseEngine):
    """Specification 064 — Intelligent Workflow Execution Engine."""

    def __init__(self) -> None:
        super().__init__(
            name="workflow_execution",
            version="1.0.0",
            description=(
                "Executes platform workflows from execution plans. Supports "
                "sequential, parallel and conditional stages, branch management, "
                "checkpoints, resume and rollback."
            ),
            tags=[
                "workflow", "stages", "checkpoint", "rollback",
                "parallel", "conditional", "resume",
            ],
            metadata={"specification": "064", "priority": "MAXIMUM CRITICAL"},
        )
        self._sched_reader = SchedulerReader()
        self._queue_reader = QueueReader()
        self._orch_reader = OrchestratorReader()
        self._ctx_reader = ExecutionContextReader()
        self._svc_reader = ServiceReader()
        self._request_reader = UserRequestReader()
        self._runner = WorkflowRunner()
        self._cache = CacheManager(enabled=True)
        self._quality_gate = QualityGate()
        self._builder = BlueprintBuilder()

    def execute(self, context: GenerationContext) -> StageResult:
        try:
            _log.info("WorkflowExecutionEngine starting (Spec 064)")

            request_data = self._request_reader.read(context)
            sched_data = self._sched_reader.read(context)
            queue_data = self._queue_reader.read(context)
            orch_data = self._orch_reader.read(context)
            ctx_data = self._ctx_reader.read(context)
            svc_data = self._svc_reader.read(context)

            sources_used = []
            sources_missing = []
            for key, data in (
                (SOURCE_USER_REQUEST, request_data),
                (SOURCE_SCHEDULER, sched_data),
                (SOURCE_QUEUE, queue_data),
                (SOURCE_ORCHESTRATOR, orch_data),
                (SOURCE_EXECUTION_CONTEXT, ctx_data),
                (SOURCE_SERVICE, svc_data),
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
                    report = WorkflowExecutionReport(**{
                        k: v for k, v in cached.items()
                        if k in WorkflowExecutionReport.__dataclass_fields__
                    })
                except Exception:
                    report = None
                if report is not None:
                    report.cache_info = self._cache.info_for_hit(cache_key)
                    context.set("workflow_execution_report", report)
                    return self.ok(
                        outputs={"workflow_execution_report": report.to_dict()},
                        metadata={"cache": "hit"},
                    )

            (
                workflow_id, stages, checkpoints, events, rollbacks, stats,
                gate_viol, resumed, rolled_back, mon_self_ok,
            ) = self._runner.execute(
                sched_data, queue_data, orch_data, ctx_data, svc_data, request_data,
            )

            self_ok = self._runner.self_verify(
                stages, checkpoints, events, gate_viol, mon_self_ok,
            )

            confidence = self._confidence(
                sources_used, sources_missing, stages, events, self_ok,
            )

            report = self._builder.build(
                workflow_id=workflow_id,
                stages=stages,
                checkpoints=checkpoints,
                events=events,
                rollbacks=rollbacks,
                stats=stats,
                sources_used=sources_used,
                sources_missing=sources_missing,
                sequential_gate_violations=gate_viol,
                resumed=resumed,
                rolled_back=rolled_back,
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
            context.set("workflow_execution_report", report)

            _log.info(
                "WorkflowExecutionEngine finished — verdict=%s stages=%d completed=%d",
                verdict, len(stages), report.completed_count,
            )

            if not passed:
                return self.failed(
                    errors=[
                        f"Workflow Execution failed quality gate "
                        f"(verdict={verdict})"
                    ],
                    outputs={"workflow_execution_report": report_dict},
                    warnings=[f.message for f in gate_findings],
                )
            return self.ok(
                outputs={"workflow_execution_report": report_dict},
                metadata={
                    "report_id": report.report_id,
                    "workflow_id": workflow_id,
                    "verdict": verdict,
                    "stage_count": len(stages),
                    "completed_count": report.completed_count,
                    "failed_count": report.failed_count,
                    "checkpoint_count": len(checkpoints),
                    "sequential_gate_violations": gate_viol,
                    "resumed": resumed,
                    "rolled_back": rolled_back,
                    "self_verification_passed": self_ok,
                    "confidence": confidence,
                },
            )
        except Exception as exc:
            _log.exception("WorkflowExecutionEngine crashed: %s", exc)
            return self.failed(
                errors=[f"WorkflowExecutionEngine error: {exc}"]
            )

    def _confidence(self, used, missing, stages, events, self_ok) -> float:
        total = len(ALL_SOURCES)
        ratio = len(used) / total if total else 0.0
        richness = min(1.0, len(stages) / 5.0)
        activity = min(1.0, len(events) / max(1, len(stages) * 2))
        penalty = 0.0 if self_ok else 0.25
        conf = (0.25 * ratio) + (0.25 * richness) + (0.30 * activity) + 0.20 - penalty
        return round(max(0.0, min(1.0, conf)), 3)


__all__ = ["WorkflowExecutionEngine"]
