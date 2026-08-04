"""
SystemMonitoringEngine — Specification 057 (CRITICAL)

Real-time platform monitoring: resources, engines, health, performance,
anomaly detection, alerts, history and trend analysis.
"""

from __future__ import annotations

import hashlib
import logging

from ....core.context import GenerationContext
from ....core.result import StageResult
from ...base.base_engine import BaseEngine
from .data_readers import (
    ResourceReader, SyncReader, OrchestratorReader, EcosystemReader,
    ExecutionContextReader, WorkspaceReader, UserRequestReader,
)
from .report_data import (
    SystemMonitoringReport, ALL_SOURCES,
    SOURCE_RESOURCE, SOURCE_SYNC, SOURCE_ORCHESTRATOR, SOURCE_ECOSYSTEM,
    SOURCE_EXECUTION_CONTEXT, SOURCE_WORKSPACE, SOURCE_USER_REQUEST,
)
from .monitor import SystemMonitor
from .cache_manager import CacheManager
from .quality_gate import QualityGate
from .blueprint_builder import BlueprintBuilder

_log = logging.getLogger("engine.system_monitoring")


class SystemMonitoringEngine(BaseEngine):
    """Specification 057 — Intelligent System Monitoring Engine."""

    def __init__(self) -> None:
        super().__init__(
            name="system_monitoring",
            version="1.0.0",
            description=(
                "Real-time monitoring of the entire platform. Tracks CPU, RAM, "
                "disk, threads, network, workspace and engines. Detects anomalies, "
                "issues alerts, records history and analyses trends before problems "
                "impact execution."
            ),
            tags=[
                "monitoring", "health", "performance", "anomaly",
                "alerts", "trends", "realtime",
            ],
            metadata={"specification": "057", "priority": "CRITICAL"},
        )
        self._resource_reader = ResourceReader()
        self._sync_reader = SyncReader()
        self._orch_reader = OrchestratorReader()
        self._eco_reader = EcosystemReader()
        self._ctx_reader = ExecutionContextReader()
        self._ws_reader = WorkspaceReader()
        self._request_reader = UserRequestReader()
        self._monitor = SystemMonitor()
        self._cache = CacheManager(enabled=True)
        self._quality_gate = QualityGate()
        self._builder = BlueprintBuilder()

    def execute(self, context: GenerationContext) -> StageResult:
        try:
            _log.info("SystemMonitoringEngine starting (Spec 057)")

            request_data = self._request_reader.read(context)
            resource_data = self._resource_reader.read(context)
            sync_data = self._sync_reader.read(context)
            orch_data = self._orch_reader.read(context)
            eco_data = self._eco_reader.read(context)
            ctx_data = self._ctx_reader.read(context)
            ws_data = self._ws_reader.read(context)

            sources_used = []
            sources_missing = []
            for key, data in (
                (SOURCE_USER_REQUEST, request_data),
                (SOURCE_RESOURCE, resource_data),
                (SOURCE_SYNC, sync_data),
                (SOURCE_ORCHESTRATOR, orch_data),
                (SOURCE_ECOSYSTEM, eco_data),
                (SOURCE_EXECUTION_CONTEXT, ctx_data),
                (SOURCE_WORKSPACE, ws_data),
            ):
                if data.available:
                    sources_used.append(key)
                else:
                    sources_missing.append(key)

            cache_payload = str(sorted(sources_used)) + str(
                (eco_data.raw or {}).get("engine_count")
                or (orch_data.raw or {}).get("task_count")
                or (resource_data.raw or {}).get("engine_count")
                or ""
            )
            cache_key = hashlib.sha256(cache_payload.encode("utf-8")).hexdigest()[:32]

            cached = self._cache.get(cache_key)
            if cached is not None:
                try:
                    report = SystemMonitoringReport(**{
                        k: v for k, v in cached.items()
                        if k in SystemMonitoringReport.__dataclass_fields__
                    })
                except Exception:
                    report = None
                if report is not None:
                    report.cache_info = self._cache.info_for_hit(cache_key)
                    context.set("system_monitoring_report", report)
                    return self.ok(
                        outputs={"system_monitoring_report": report.to_dict()},
                        metadata={"cache": "hit"},
                    )

            (
                metrics, statuses, health, performance,
                anomalies, alerts, history, trend, mon_self_ok,
            ) = self._monitor.monitor(
                resource_data, sync_data, orch_data, eco_data,
                ctx_data, ws_data, request_data,
            )

            self_ok = self._monitor.self_verify(
                metrics, statuses, health, mon_self_ok,
            )

            confidence = self._confidence(
                sources_used, sources_missing, statuses, health, self_ok,
            )

            report = self._builder.build(
                metrics=metrics,
                engine_statuses=statuses,
                health=health,
                performance=performance,
                anomalies=anomalies,
                alerts=alerts,
                history=history,
                trend=trend,
                sources_used=sources_used,
                sources_missing=sources_missing,
                self_verification_passed=self_ok,
                monitoring_self_ok=mon_self_ok,
                confidence=confidence,
            )

            gate_findings, passed, verdict = self._quality_gate.validate(report)
            report.findings.extend(gate_findings)
            report.verdict = verdict
            report.readiness_status = verdict
            report.self_verification_passed = self_ok
            report.monitoring_self_ok = mon_self_ok

            report_dict = report.to_dict()
            report.cache_info = self._cache.put(cache_key, report_dict)
            context.set("system_monitoring_report", report)

            _log.info(
                "SystemMonitoringEngine finished — verdict=%s engines=%d "
                "anomalies=%d alerts=%d health=%.2f",
                verdict, len(statuses), len(anomalies), len(alerts),
                health.overall_score,
            )

            if not passed:
                return self.failed(
                    errors=[
                        f"System Monitoring failed quality gate "
                        f"(verdict={verdict})"
                    ],
                    outputs={"system_monitoring_report": report_dict},
                    warnings=[f.message for f in gate_findings],
                )
            return self.ok(
                outputs={"system_monitoring_report": report_dict},
                metadata={
                    "report_id": report.report_id,
                    "verdict": verdict,
                    "engine_count": len(statuses),
                    "anomaly_count": len(anomalies),
                    "alert_count": len(alerts),
                    "critical_alert_count": report.critical_alert_count,
                    "health_score": health.overall_score,
                    "trend": trend.direction,
                    "self_verification_passed": self_ok,
                    "confidence": confidence,
                },
            )
        except Exception as exc:
            _log.exception("SystemMonitoringEngine crashed: %s", exc)
            return self.failed(errors=[f"SystemMonitoringEngine error: {exc}"])

    def _confidence(self, used, missing, statuses, health, self_ok) -> float:
        total = len(ALL_SOURCES)
        ratio = len(used) / total if total else 0.0
        richness = min(1.0, len(statuses) / 5.0)
        health_f = max(0.0, min(1.0, health.overall_score)) if health else 0.0
        penalty = 0.0 if self_ok else 0.25
        conf = (0.25 * ratio) + (0.25 * richness) + (0.30 * health_f) + 0.20 - penalty
        return round(max(0.0, min(1.0, conf)), 3)


__all__ = ["SystemMonitoringEngine"]
