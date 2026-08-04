"""
ServiceManagementEngine — Specification 061 (MAXIMUM CRITICAL)

Central service registry and lifecycle for internal platform services.
Register, start/stop/restart, dependency order, health, recovery,
isolation, load and resource allocation. No service may run unregistered.
"""

from __future__ import annotations

import hashlib
import logging

from ....core.context import GenerationContext
from ....core.result import StageResult
from ...base.base_engine import BaseEngine
from .data_readers import (
    SecurityReader, ConfigReader, MonitoringReader, ResourceReader,
    ExecutionContextReader, EcosystemReader, UserRequestReader,
)
from .report_data import (
    ServiceManagementReport, ALL_SOURCES,
    SOURCE_SECURITY, SOURCE_CONFIG, SOURCE_MONITORING, SOURCE_RESOURCE,
    SOURCE_EXECUTION_CONTEXT, SOURCE_ECOSYSTEM, SOURCE_USER_REQUEST,
)
from .service_manager import ServiceManager
from .cache_manager import CacheManager
from .quality_gate import QualityGate
from .blueprint_builder import BlueprintBuilder

_log = logging.getLogger("engine.service_management")


class ServiceManagementEngine(BaseEngine):
    """Specification 061 — Intelligent Service Management Engine."""

    def __init__(self) -> None:
        super().__init__(
            name="service_management",
            version="1.0.0",
            description=(
                "Central management of internal platform services. Registry, "
                "lifecycle (init/start/pause/resume/restart/shutdown), dependency "
                "validation, health monitoring, automatic recovery, isolation, "
                "load monitoring and resource allocation."
            ),
            tags=[
                "service", "lifecycle", "registry", "health",
                "recovery", "isolation", "dependencies",
            ],
            metadata={"specification": "061", "priority": "MAXIMUM CRITICAL"},
        )
        self._sec_reader = SecurityReader()
        self._cfg_reader = ConfigReader()
        self._mon_reader = MonitoringReader()
        self._res_reader = ResourceReader()
        self._ctx_reader = ExecutionContextReader()
        self._eco_reader = EcosystemReader()
        self._request_reader = UserRequestReader()
        self._manager = ServiceManager()
        self._cache = CacheManager(enabled=True)
        self._quality_gate = QualityGate()
        self._builder = BlueprintBuilder()

    def execute(self, context: GenerationContext) -> StageResult:
        try:
            _log.info("ServiceManagementEngine starting (Spec 061)")

            request_data = self._request_reader.read(context)
            sec_data = self._sec_reader.read(context)
            cfg_data = self._cfg_reader.read(context)
            mon_data = self._mon_reader.read(context)
            res_data = self._res_reader.read(context)
            ctx_data = self._ctx_reader.read(context)
            eco_data = self._eco_reader.read(context)

            sources_used = []
            sources_missing = []
            for key, data in (
                (SOURCE_USER_REQUEST, request_data),
                (SOURCE_SECURITY, sec_data),
                (SOURCE_CONFIG, cfg_data),
                (SOURCE_MONITORING, mon_data),
                (SOURCE_RESOURCE, res_data),
                (SOURCE_EXECUTION_CONTEXT, ctx_data),
                (SOURCE_ECOSYSTEM, eco_data),
            ):
                if data.available:
                    sources_used.append(key)
                else:
                    sources_missing.append(key)

            cache_payload = str(sorted(sources_used)) + str(
                (eco_data.raw or {}).get("engine_count")
                or (request_data.raw or {}).get("project_id")
                or ""
            )
            cache_key = hashlib.sha256(cache_payload.encode("utf-8")).hexdigest()[:32]

            cached = self._cache.get(cache_key)
            if cached is not None:
                try:
                    report = ServiceManagementReport(**{
                        k: v for k, v in cached.items()
                        if k in ServiceManagementReport.__dataclass_fields__
                    })
                except Exception:
                    report = None
                if report is not None:
                    report.cache_info = self._cache.info_for_hit(cache_key)
                    context.set("service_management_report", report)
                    return self.ok(
                        outputs={"service_management_report": report.to_dict()},
                        metadata={"cache": "hit"},
                    )

            (
                services, health, events, recoveries, allocations, loads,
                unregistered, dep_violations, mon_self_ok,
            ) = self._manager.manage(
                sec_data, cfg_data, mon_data, res_data,
                ctx_data, eco_data, request_data,
            )

            self_ok = self._manager.self_verify(
                services, events, unregistered, dep_violations, mon_self_ok,
            )

            confidence = self._confidence(
                sources_used, sources_missing, services, events, self_ok,
            )

            report = self._builder.build(
                services=services,
                health=health,
                lifecycle_events=events,
                recoveries=recoveries,
                allocations=allocations,
                loads=loads,
                sources_used=sources_used,
                sources_missing=sources_missing,
                unregistered_attempts=unregistered,
                dependency_violations=dep_violations,
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
            context.set("service_management_report", report)

            _log.info(
                "ServiceManagementEngine finished — verdict=%s services=%d "
                "started=%d failed=%d",
                verdict, len(services), report.started_count, report.failed_count,
            )

            if not passed:
                return self.failed(
                    errors=[
                        f"Service Management failed quality gate "
                        f"(verdict={verdict})"
                    ],
                    outputs={"service_management_report": report_dict},
                    warnings=[f.message for f in gate_findings],
                )
            return self.ok(
                outputs={"service_management_report": report_dict},
                metadata={
                    "report_id": report.report_id,
                    "verdict": verdict,
                    "service_count": len(services),
                    "started_count": report.started_count,
                    "failed_count": report.failed_count,
                    "recovery_count": report.recovery_count,
                    "unregistered_attempts": unregistered,
                    "dependency_violations": dep_violations,
                    "self_verification_passed": self_ok,
                    "confidence": confidence,
                },
            )
        except Exception as exc:
            _log.exception("ServiceManagementEngine crashed: %s", exc)
            return self.failed(
                errors=[f"ServiceManagementEngine error: {exc}"]
            )

    def _confidence(self, used, missing, services, events, self_ok) -> float:
        total = len(ALL_SOURCES)
        ratio = len(used) / total if total else 0.0
        richness = min(1.0, len(services) / 5.0)
        lifecycle = min(1.0, len(events) / max(1, len(services) * 2))
        penalty = 0.0 if self_ok else 0.25
        conf = (0.25 * ratio) + (0.25 * richness) + (0.30 * lifecycle) + 0.20 - penalty
        return round(max(0.0, min(1.0, conf)), 3)


__all__ = ["ServiceManagementEngine"]
