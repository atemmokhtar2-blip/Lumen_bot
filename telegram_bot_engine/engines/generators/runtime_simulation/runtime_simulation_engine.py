"""
RuntimeSimulationEngine — Specification 040 (ULTRA CRITICAL)

Simulates full project runtime (startup, Telegram flows, failures, stress)
before real delivery. Runtime errors, crashes, failures or leaks block.
"""

from __future__ import annotations

import hashlib
import logging

from ....core.context import GenerationContext
from ....core.result import StageResult
from ...base.base_engine import BaseEngine
from .data_readers import (
    StaticAnalysisReader, ArchitectureComplianceReader, PerformanceReader,
    SecurityReader, CodeRefactoringReader, ProjectContextReader,
)
from .report_data import (
    RuntimeSimulationReport, ALL_SOURCES,
    SOURCE_STATIC_ANALYSIS, SOURCE_ARCHITECTURE_COMPLIANCE,
    SOURCE_PERFORMANCE, SOURCE_SECURITY, SOURCE_CODE_REFACTORING,
    SOURCE_PROJECT_CONTEXT,
)
from .simulator import RuntimeSimulator
from .cache_manager import CacheManager
from .quality_gate import QualityGate
from .blueprint_builder import BlueprintBuilder

_log = logging.getLogger("engine.runtime_simulation")


class RuntimeSimulationEngine(BaseEngine):
    """Specification 040 — Intelligent Runtime Simulation & Verification Engine."""

    def __init__(self) -> None:
        super().__init__(
            name="runtime_simulation",
            version="1.0.0",
            description=(
                "Simulates startup, Telegram flows, failures and stress in an isolated "
                "logical runtime. Blocks on crashes, critical failures or memory leaks."
            ),
            tags=["runtime", "simulation", "telegram", "stress", "verification"],
            metadata={"specification": "040", "priority": "ULTRA_CRITICAL"},
        )
        self._static_reader = StaticAnalysisReader()
        self._arch_reader = ArchitectureComplianceReader()
        self._perf_reader = PerformanceReader()
        self._sec_reader = SecurityReader()
        self._ref_reader = CodeRefactoringReader()
        self._ctx_reader = ProjectContextReader()
        self._simulator = RuntimeSimulator()
        self._cache = CacheManager(enabled=True)
        self._quality_gate = QualityGate()
        self._builder = BlueprintBuilder()

    def execute(self, context: GenerationContext) -> StageResult:
        try:
            _log.info("RuntimeSimulationEngine starting (Spec 040)")

            static_data = self._static_reader.read(context)
            arch_data = self._arch_reader.read(context)
            perf_data = self._perf_reader.read(context)
            sec_data = self._sec_reader.read(context)
            ref_data = self._ref_reader.read(context)
            ctx_data = self._ctx_reader.read(context)

            sources_used = []
            sources_missing = []
            for key, data in (
                (SOURCE_STATIC_ANALYSIS, static_data),
                (SOURCE_ARCHITECTURE_COMPLIANCE, arch_data),
                (SOURCE_PERFORMANCE, perf_data),
                (SOURCE_SECURITY, sec_data),
                (SOURCE_CODE_REFACTORING, ref_data),
                (SOURCE_PROJECT_CONTEXT, ctx_data),
            ):
                if data.available:
                    sources_used.append(key)
                else:
                    sources_missing.append(key)

            cache_payload = str(sorted(sources_used)) + str(
                (static_data.raw or {}).get("open_critical_count", 0)
            ) + str((sec_data.raw or {}).get("open_critical_count", 0))
            cache_key = hashlib.sha256(cache_payload.encode("utf-8")).hexdigest()[:32]

            cached = self._cache.get(cache_key)
            if cached is not None:
                try:
                    report = RuntimeSimulationReport(**{
                        k: v for k, v in cached.items()
                        if k in RuntimeSimulationReport.__dataclass_fields__
                    })
                except Exception:
                    report = None
                if report is not None:
                    report.cache_info = self._cache.info_for_hit(cache_key)
                    context.set("runtime_simulation_report", report)
                    return self.ok(
                        outputs={"runtime_simulation_report": report.to_dict()},
                        metadata={"cache": "hit"},
                    )

            (
                events, stress, failures, resources, score,
                startup_ok, leak_detected, runs,
            ) = self._simulator.run(
                static_data, arch_data, perf_data, sec_data, ref_data,
            )

            self_ok = self._simulator.self_verify(events, startup_ok, leak_detected)

            confidence = self._confidence(
                sources_used, sources_missing, events, score.overall, startup_ok,
            )

            report = self._builder.build(
                events=events,
                stress_results=stress,
                failures=failures,
                resources=resources,
                score=score,
                sources_used=sources_used,
                sources_missing=sources_missing,
                startup_ok=startup_ok,
                leak_detected=leak_detected,
                self_verification_passed=self_ok,
                runs_completed=runs,
                confidence=confidence,
            )

            gate_findings, passed, verdict = self._quality_gate.validate(report)
            report.findings.extend(gate_findings)
            report.verdict = verdict
            report.readiness_status = verdict
            report.self_verification_passed = self_ok

            report_dict = report.to_dict()
            report.cache_info = self._cache.put(cache_key, report_dict)
            context.set("runtime_simulation_report", report)

            _log.info(
                "RuntimeSimulationEngine finished — verdict=%s events=%d "
                "failed=%d score=%.1f startup_ok=%s",
                verdict, len(events), report.failed_event_count,
                score.overall, startup_ok,
            )

            if not passed:
                return self.failed(
                    errors=[
                        f"Runtime Simulation failed quality gate (verdict={verdict})"
                    ],
                    outputs={"runtime_simulation_report": report_dict},
                    warnings=[f.message for f in gate_findings],
                )
            return self.ok(
                outputs={"runtime_simulation_report": report_dict},
                metadata={
                    "report_id": report.report_id,
                    "verdict": verdict,
                    "event_count": len(events),
                    "failed_event_count": report.failed_event_count,
                    "crash_count": report.crash_count,
                    "startup_ok": startup_ok,
                    "leak_detected": leak_detected,
                    "runtime_score": score.overall,
                    "self_verification_passed": self_ok,
                    "confidence": confidence,
                },
            )
        except Exception as exc:
            _log.exception("RuntimeSimulationEngine crashed: %s", exc)
            return self.failed(errors=[f"RuntimeSimulationEngine error: {exc}"])

    def _confidence(self, used, missing, events, overall, startup_ok) -> float:
        total = len(ALL_SOURCES)
        ratio = len(used) / total if total else 0.0
        failed = sum(1 for e in events if getattr(e, "status", "") == "failed")
        penalty = min(0.5, failed * 0.05 + (0.2 if not startup_ok else 0.0))
        score_factor = overall / 100.0
        conf = (0.30 * ratio) + (0.40 * score_factor) + 0.30 - penalty
        return round(max(0.0, min(1.0, conf)), 3)


__all__ = ["RuntimeSimulationEngine"]
