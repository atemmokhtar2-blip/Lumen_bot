"""
EngineOrchestratorEngine — Specification 053 (MAXIMUM CRITICAL)

Central orchestrator of all platform engines. No engine starts on its own.
Plans, schedules, monitors, retries, detects deadlocks and replans.
"""

from __future__ import annotations

import hashlib
import logging

from ....core.context import GenerationContext
from ....core.result import StageResult
from ...base.base_engine import BaseEngine
from .data_readers import (
    EcosystemReader, EnvironmentReader, DependencyReader,
    ProjectContextReader, UserRequestReader,
)
from .report_data import (
    EngineOrchestratorReport, ALL_SOURCES,
    SOURCE_ECOSYSTEM, SOURCE_ENVIRONMENT, SOURCE_DEPENDENCY,
    SOURCE_PROJECT_CONTEXT, SOURCE_USER_REQUEST,
)
from .orchestrator import OrchestratorCore
from .cache_manager import CacheManager
from .quality_gate import QualityGate
from .blueprint_builder import BlueprintBuilder

_log = logging.getLogger("engine.engine_orchestrator")


class EngineOrchestratorEngine(BaseEngine):
    """Specification 053 — Intelligent Engine Orchestrator."""

    def __init__(self) -> None:
        super().__init__(
            name="engine_orchestrator",
            version="1.0.0",
            description=(
                "Central orchestrator: execution planning, dependency resolution, "
                "parallel scheduling, failure isolation, retry, deadlock detection "
                "and dynamic replanning. All engine calls go through this layer."
            ),
            tags=["orchestrator", "scheduler", "execution", "deadlock", "retry"],
            metadata={"specification": "053", "priority": "MAXIMUM_CRITICAL"},
        )
        self._eco_reader = EcosystemReader()
        self._env_reader = EnvironmentReader()
        self._dep_reader = DependencyReader()
        self._ctx_reader = ProjectContextReader()
        self._request_reader = UserRequestReader()
        self._core = OrchestratorCore()
        self._cache = CacheManager(enabled=True)
        self._quality_gate = QualityGate()
        self._builder = BlueprintBuilder()

    def execute(self, context: GenerationContext) -> StageResult:
        try:
            _log.info("EngineOrchestratorEngine starting (Spec 053)")

            request_data = self._request_reader.read(context)
            eco_data = self._eco_reader.read(context)
            env_data = self._env_reader.read(context)
            dep_data = self._dep_reader.read(context)
            ctx_data = self._ctx_reader.read(context)

            sources_used = []
            sources_missing = []
            for key, data in (
                (SOURCE_USER_REQUEST, request_data),
                (SOURCE_ECOSYSTEM, eco_data),
                (SOURCE_ENVIRONMENT, env_data),
                (SOURCE_DEPENDENCY, dep_data),
                (SOURCE_PROJECT_CONTEXT, ctx_data),
            ):
                if data.available:
                    sources_used.append(key)
                else:
                    sources_missing.append(key)

            cache_payload = str(sorted(sources_used)) + str(
                (request_data.raw or {}).get("engines")
                or (eco_data.raw or {}).get("engine_count")
                or ""
            )
            cache_key = hashlib.sha256(cache_payload.encode("utf-8")).hexdigest()[:32]

            cached = self._cache.get(cache_key)
            if cached is not None:
                try:
                    report = EngineOrchestratorReport(**{
                        k: v for k, v in cached.items()
                        if k in EngineOrchestratorReport.__dataclass_fields__
                    })
                except Exception:
                    report = None
                if report is not None:
                    report.cache_info = self._cache.info_for_hit(cache_key)
                    context.set("engine_orchestrator_report", report)
                    return self.ok(
                        outputs={"engine_orchestrator_report": report.to_dict()},
                        metadata={"cache": "hit"},
                    )

            plan, history, resources, deadlocks, metrics, replanned = self._core.run(
                request_data, eco_data, ctx_data,
            )

            self_ok = self._core.self_verify(plan, history, deadlocks)

            confidence = self._confidence(
                sources_used, sources_missing, plan, metrics, self_ok,
            )

            report = self._builder.build(
                plan=plan,
                history=history,
                resources=resources,
                deadlocks=deadlocks,
                metrics=metrics,
                sources_used=sources_used,
                sources_missing=sources_missing,
                replanned=replanned,
                self_verification_passed=self_ok,
                confidence=confidence,
            )

            gate_findings, passed, verdict = self._quality_gate.validate(report)
            report.findings.extend(gate_findings)
            report.verdict = verdict
            report.readiness_status = verdict
            report.self_verification_passed = self_ok
            report.replanned = replanned

            report_dict = report.to_dict()
            report.cache_info = self._cache.put(cache_key, report_dict)
            context.set("engine_orchestrator_report", report)

            _log.info(
                "EngineOrchestratorEngine finished — verdict=%s tasks=%d "
                "success_rate=%.1f replanned=%s",
                verdict, len(plan), metrics.success_rate, replanned,
            )

            if not passed:
                return self.failed(
                    errors=[
                        f"Engine Orchestrator failed quality gate "
                        f"(verdict={verdict})"
                    ],
                    outputs={"engine_orchestrator_report": report_dict},
                    warnings=[f.message for f in gate_findings],
                )
            return self.ok(
                outputs={"engine_orchestrator_report": report_dict},
                metadata={
                    "report_id": report.report_id,
                    "verdict": verdict,
                    "task_count": len(plan),
                    "failure_count": report.failure_count,
                    "deadlock_count": report.deadlock_count,
                    "success_rate": metrics.success_rate,
                    "parallel_waves": metrics.parallel_waves,
                    "replanned": replanned,
                    "self_verification_passed": self_ok,
                    "confidence": confidence,
                },
            )
        except Exception as exc:
            _log.exception("EngineOrchestratorEngine crashed: %s", exc)
            return self.failed(errors=[f"EngineOrchestratorEngine error: {exc}"])

    def _confidence(self, used, missing, plan, metrics, self_ok) -> float:
        total = len(ALL_SOURCES)
        ratio = len(used) / total if total else 0.0
        richness = min(1.0, len(plan) / 8.0)
        success_f = (metrics.success_rate / 100.0) if metrics else 0.0
        penalty = 0.0 if self_ok else 0.25
        conf = (0.25 * ratio) + (0.25 * richness) + (0.30 * success_f) + 0.20 - penalty
        return round(max(0.0, min(1.0, conf)), 3)


__all__ = ["EngineOrchestratorEngine"]
