"""
ResourceManagementEngine — Specification 056 (CRITICAL)

Manages CPU, RAM, storage and threads for all platform engines.
Allocation, monitoring, limits, leak detection, cleanup and recovery.
"""

from __future__ import annotations

import hashlib
import logging

from ....core.context import GenerationContext
from ....core.result import StageResult
from ...base.base_engine import BaseEngine
from .data_readers import (
    SyncReader, OrchestratorReader, EcosystemReader,
    ExecutionContextReader, UserRequestReader,
)
from .report_data import (
    ResourceManagementReport, ALL_SOURCES,
    SOURCE_SYNC, SOURCE_ORCHESTRATOR, SOURCE_ECOSYSTEM,
    SOURCE_EXECUTION_CONTEXT, SOURCE_USER_REQUEST,
)
from .resource_manager import ResourceManager
from .cache_manager import CacheManager
from .quality_gate import QualityGate
from .blueprint_builder import BlueprintBuilder

_log = logging.getLogger("engine.resource_management")


class ResourceManagementEngine(BaseEngine):
    """Specification 056 — Intelligent Resource Management Engine."""

    def __init__(self) -> None:
        super().__init__(
            name="resource_management",
            version="1.0.0",
            description=(
                "Manages CPU, RAM, storage and threads across all engines. "
                "Allocation, monitoring, optimization, limits, leak detection, "
                "automatic cleanup and recovery on resource exhaustion."
            ),
            tags=["resource", "cpu", "memory", "threads", "limits", "cleanup"],
            metadata={"specification": "056", "priority": "CRITICAL"},
        )
        self._sync_reader = SyncReader()
        self._orch_reader = OrchestratorReader()
        self._eco_reader = EcosystemReader()
        self._ctx_reader = ExecutionContextReader()
        self._request_reader = UserRequestReader()
        self._manager = ResourceManager()
        self._cache = CacheManager(enabled=True)
        self._quality_gate = QualityGate()
        self._builder = BlueprintBuilder()

    def execute(self, context: GenerationContext) -> StageResult:
        try:
            _log.info("ResourceManagementEngine starting (Spec 056)")

            request_data = self._request_reader.read(context)
            sync_data = self._sync_reader.read(context)
            orch_data = self._orch_reader.read(context)
            eco_data = self._eco_reader.read(context)
            ctx_data = self._ctx_reader.read(context)

            sources_used = []
            sources_missing = []
            for key, data in (
                (SOURCE_USER_REQUEST, request_data),
                (SOURCE_SYNC, sync_data),
                (SOURCE_ORCHESTRATOR, orch_data),
                (SOURCE_ECOSYSTEM, eco_data),
                (SOURCE_EXECUTION_CONTEXT, ctx_data),
            ):
                if data.available:
                    sources_used.append(key)
                else:
                    sources_missing.append(key)

            cache_payload = str(sorted(sources_used)) + str(
                (eco_data.raw or {}).get("engine_count")
                or (orch_data.raw or {}).get("task_count")
                or ""
            )
            cache_key = hashlib.sha256(cache_payload.encode("utf-8")).hexdigest()[:32]

            cached = self._cache.get(cache_key)
            if cached is not None:
                try:
                    report = ResourceManagementReport(**{
                        k: v for k, v in cached.items()
                        if k in ResourceManagementReport.__dataclass_fields__
                    })
                except Exception:
                    report = None
                if report is not None:
                    report.cache_info = self._cache.info_for_hit(cache_key)
                    context.set("resource_management_report", report)
                    return self.ok(
                        outputs={"resource_management_report": report.to_dict()},
                        metadata={"cache": "hit"},
                    )

            quotas, usage, leaks, cleanups, system, recovered = self._manager.manage(
                request_data, orch_data, eco_data, ctx_data, sync_data,
            )

            self_ok = self._manager.self_verify(quotas, usage, leaks, system)

            confidence = self._confidence(
                sources_used, sources_missing, quotas, system, self_ok,
            )

            report = self._builder.build(
                quotas=quotas,
                usage=usage,
                leaks=leaks,
                cleanups=cleanups,
                system=system,
                sources_used=sources_used,
                sources_missing=sources_missing,
                recovered=recovered,
                self_verification_passed=self_ok,
                confidence=confidence,
            )

            gate_findings, passed, verdict = self._quality_gate.validate(report)
            report.findings.extend(gate_findings)
            report.verdict = verdict
            report.readiness_status = verdict
            report.self_verification_passed = self_ok
            report.recovered = recovered

            report_dict = report.to_dict()
            report.cache_info = self._cache.put(cache_key, report_dict)
            context.set("resource_management_report", report)

            _log.info(
                "ResourceManagementEngine finished — verdict=%s engines=%d "
                "over=%d leaks=%d",
                verdict, len(quotas), report.over_limit_count, report.leak_count,
            )

            if not passed:
                return self.failed(
                    errors=[
                        f"Resource Management failed quality gate "
                        f"(verdict={verdict})"
                    ],
                    outputs={"resource_management_report": report_dict},
                    warnings=[f.message for f in gate_findings],
                )
            return self.ok(
                outputs={"resource_management_report": report_dict},
                metadata={
                    "report_id": report.report_id,
                    "verdict": verdict,
                    "engine_count": len(quotas),
                    "over_limit_count": report.over_limit_count,
                    "leak_count": report.leak_count,
                    "total_cpu_percent": system.total_cpu_percent,
                    "available_ram_mb": system.available_ram_mb,
                    "recovered": recovered,
                    "self_verification_passed": self_ok,
                    "confidence": confidence,
                },
            )
        except Exception as exc:
            _log.exception("ResourceManagementEngine crashed: %s", exc)
            return self.failed(errors=[f"ResourceManagementEngine error: {exc}"])

    def _confidence(self, used, missing, quotas, system, self_ok) -> float:
        total = len(ALL_SOURCES)
        ratio = len(used) / total if total else 0.0
        richness = min(1.0, len(quotas) / 5.0)
        headroom = min(1.0, system.available_cpu_percent / 30.0) if system else 0.0
        penalty = 0.0 if self_ok else 0.25
        conf = (0.25 * ratio) + (0.25 * richness) + (0.30 * headroom) + 0.20 - penalty
        return round(max(0.0, min(1.0, conf)), 3)


__all__ = ["ResourceManagementEngine"]
