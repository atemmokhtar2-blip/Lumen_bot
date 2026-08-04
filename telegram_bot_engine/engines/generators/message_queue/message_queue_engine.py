"""
MessageQueueEngine — Specification 062 (MAXIMUM CRITICAL)

Central message queue between engines and services. Priority/FIFO/delayed/
retry queues, reliable delivery, deduplication, persistence, dead-letter
queue and ordering guarantees.
"""

from __future__ import annotations

import hashlib
import logging

from ....core.context import GenerationContext
from ....core.result import StageResult
from ...base.base_engine import BaseEngine
from .data_readers import (
    ServiceReader, SecurityReader, MonitoringReader,
    OrchestratorReader, ExecutionContextReader, UserRequestReader,
)
from .report_data import (
    MessageQueueReport, ALL_SOURCES,
    SOURCE_SERVICE, SOURCE_SECURITY, SOURCE_MONITORING,
    SOURCE_ORCHESTRATOR, SOURCE_EXECUTION_CONTEXT, SOURCE_USER_REQUEST,
)
from .queue_manager import QueueManager
from .cache_manager import CacheManager
from .quality_gate import QualityGate
from .blueprint_builder import BlueprintBuilder

_log = logging.getLogger("engine.message_queue")


class MessageQueueEngine(BaseEngine):
    """Specification 062 — Intelligent Message Queue Engine."""

    def __init__(self) -> None:
        super().__init__(
            name="message_queue",
            version="1.0.0",
            description=(
                "Central message queue for inter-engine and inter-service traffic. "
                "Priority, FIFO, delayed and retry queues with reliable delivery, "
                "deduplication, persistence, dead-letter queue and ordering."
            ),
            tags=[
                "queue", "messaging", "delivery", "retry",
                "dlq", "dedupe", "ordering", "persistence",
            ],
            metadata={"specification": "062", "priority": "MAXIMUM CRITICAL"},
        )
        self._svc_reader = ServiceReader()
        self._sec_reader = SecurityReader()
        self._mon_reader = MonitoringReader()
        self._orch_reader = OrchestratorReader()
        self._ctx_reader = ExecutionContextReader()
        self._request_reader = UserRequestReader()
        self._manager = QueueManager()
        self._cache = CacheManager(enabled=True)
        self._quality_gate = QualityGate()
        self._builder = BlueprintBuilder()

    def execute(self, context: GenerationContext) -> StageResult:
        try:
            _log.info("MessageQueueEngine starting (Spec 062)")

            request_data = self._request_reader.read(context)
            svc_data = self._svc_reader.read(context)
            sec_data = self._sec_reader.read(context)
            mon_data = self._mon_reader.read(context)
            orch_data = self._orch_reader.read(context)
            ctx_data = self._ctx_reader.read(context)

            sources_used = []
            sources_missing = []
            for key, data in (
                (SOURCE_USER_REQUEST, request_data),
                (SOURCE_SERVICE, svc_data),
                (SOURCE_SECURITY, sec_data),
                (SOURCE_MONITORING, mon_data),
                (SOURCE_ORCHESTRATOR, orch_data),
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
                    report = MessageQueueReport(**{
                        k: v for k, v in cached.items()
                        if k in MessageQueueReport.__dataclass_fields__
                    })
                except Exception:
                    report = None
                if report is not None:
                    report.cache_info = self._cache.info_for_hit(cache_key)
                    context.set("message_queue_report", report)
                    return self.ok(
                        outputs={"message_queue_report": report.to_dict()},
                        metadata={"cache": "hit"},
                    )

            (
                messages, deliveries, retries, dead, stats,
                lost, duplicates, mon_self_ok,
            ) = self._manager.process(
                svc_data, sec_data, mon_data, orch_data, ctx_data, request_data,
            )

            self_ok = self._manager.self_verify(
                messages, deliveries, dead, lost, duplicates, mon_self_ok,
            )

            confidence = self._confidence(
                sources_used, sources_missing, messages, deliveries, self_ok,
            )

            report = self._builder.build(
                messages=messages,
                deliveries=deliveries,
                retries=retries,
                dead_letters=dead,
                stats=stats,
                sources_used=sources_used,
                sources_missing=sources_missing,
                lost_count=lost,
                duplicate_count=duplicates,
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
            context.set("message_queue_report", report)

            _log.info(
                "MessageQueueEngine finished — verdict=%s msgs=%d delivered=%d dlq=%d",
                verdict, len(messages), report.delivered_count, report.dlq_count,
            )

            if not passed:
                return self.failed(
                    errors=[
                        f"Message Queue failed quality gate "
                        f"(verdict={verdict})"
                    ],
                    outputs={"message_queue_report": report_dict},
                    warnings=[f.message for f in gate_findings],
                )
            return self.ok(
                outputs={"message_queue_report": report_dict},
                metadata={
                    "report_id": report.report_id,
                    "verdict": verdict,
                    "message_count": len(messages),
                    "delivered_count": report.delivered_count,
                    "failed_count": report.failed_count,
                    "retry_count": report.retry_count,
                    "dlq_count": report.dlq_count,
                    "duplicate_count": duplicates,
                    "lost_count": lost,
                    "self_verification_passed": self_ok,
                    "confidence": confidence,
                },
            )
        except Exception as exc:
            _log.exception("MessageQueueEngine crashed: %s", exc)
            return self.failed(errors=[f"MessageQueueEngine error: {exc}"])

    def _confidence(self, used, missing, messages, deliveries, self_ok) -> float:
        total = len(ALL_SOURCES)
        ratio = len(used) / total if total else 0.0
        richness = min(1.0, len(messages) / 5.0)
        delivery = min(1.0, len(deliveries) / max(1, len(messages)))
        penalty = 0.0 if self_ok else 0.25
        conf = (0.25 * ratio) + (0.25 * richness) + (0.30 * delivery) + 0.20 - penalty
        return round(max(0.0, min(1.0, conf)), 3)


__all__ = ["MessageQueueEngine"]
