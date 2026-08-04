"""
E2EScenarioTestingEngine — Specification 044 (ULTRA CRITICAL)

Runs end-to-end scenarios as real users would: virtual users, Telegram
interactions, negative/edge/load/recovery. Any failed scenario blocks.
"""

from __future__ import annotations

import hashlib
import logging

from ....core.context import GenerationContext
from ....core.result import StageResult
from ...base.base_engine import BaseEngine
from .data_readers import (
    UnitTestReader, IntegrationReader, RuntimeReader,
    ArchitectureReader, SelfHealingReader, ProjectContextReader,
)
from .report_data import (
    E2EScenarioTestingReport, ALL_SOURCES,
    SOURCE_UNIT_TEST, SOURCE_INTEGRATION, SOURCE_RUNTIME,
    SOURCE_ARCHITECTURE, SOURCE_SELF_HEALING, SOURCE_PROJECT_CONTEXT,
)
from .runner import E2EScenarioRunner
from .cache_manager import CacheManager
from .quality_gate import QualityGate
from .blueprint_builder import BlueprintBuilder

_log = logging.getLogger("engine.e2e_scenario_testing")


class E2EScenarioTestingEngine(BaseEngine):
    """Specification 044 — Intelligent End-to-End Scenario Testing Engine."""

    def __init__(self) -> None:
        super().__init__(
            name="e2e_scenario_testing",
            version="1.0.0",
            description=(
                "End-to-end scenario testing with virtual users, Telegram "
                "interactions, negative/edge/load/recovery paths. Blocks on any "
                "failed scenario."
            ),
            tags=["e2e", "scenario", "telegram", "load", "ux", "qa"],
            metadata={"specification": "044", "priority": "ULTRA_CRITICAL"},
        )
        self._unit_reader = UnitTestReader()
        self._integration_reader = IntegrationReader()
        self._runtime_reader = RuntimeReader()
        self._arch_reader = ArchitectureReader()
        self._heal_reader = SelfHealingReader()
        self._ctx_reader = ProjectContextReader()
        self._runner = E2EScenarioRunner()
        self._cache = CacheManager(enabled=True)
        self._quality_gate = QualityGate()
        self._builder = BlueprintBuilder()

    def execute(self, context: GenerationContext) -> StageResult:
        try:
            _log.info("E2EScenarioTestingEngine starting (Spec 044)")

            unit_data = self._unit_reader.read(context)
            integration_data = self._integration_reader.read(context)
            runtime_data = self._runtime_reader.read(context)
            arch_data = self._arch_reader.read(context)
            heal_data = self._heal_reader.read(context)
            ctx_data = self._ctx_reader.read(context)

            sources_used = []
            sources_missing = []
            for key, data in (
                (SOURCE_UNIT_TEST, unit_data),
                (SOURCE_INTEGRATION, integration_data),
                (SOURCE_RUNTIME, runtime_data),
                (SOURCE_ARCHITECTURE, arch_data),
                (SOURCE_SELF_HEALING, heal_data),
                (SOURCE_PROJECT_CONTEXT, ctx_data),
            ):
                if data.available:
                    sources_used.append(key)
                else:
                    sources_missing.append(key)

            cache_payload = str(sorted(sources_used)) + str(
                (unit_data.raw or {}).get("failure_count", 0)
            ) + str((integration_data.raw or {}).get("failed_count", 0))
            cache_key = hashlib.sha256(cache_payload.encode("utf-8")).hexdigest()[:32]

            cached = self._cache.get(cache_key)
            if cached is not None:
                try:
                    report = E2EScenarioTestingReport(**{
                        k: v for k, v in cached.items()
                        if k in E2EScenarioTestingReport.__dataclass_fields__
                    })
                except Exception:
                    report = None
                if report is not None:
                    report.cache_info = self._cache.info_for_hit(cache_key)
                    context.set("e2e_scenario_testing_report", report)
                    return self.ok(
                        outputs={"e2e_scenario_testing_report": report.to_dict()},
                        metadata={"cache": "hit"},
                    )

            users, scenarios, load_results, recoveries, ux, runs = self._runner.run(
                unit_data, integration_data, runtime_data, arch_data, heal_data,
            )

            self_ok = self._runner.self_verify(scenarios)

            confidence = self._confidence(
                sources_used, sources_missing, scenarios, ux.overall,
            )

            report = self._builder.build(
                users=users,
                scenarios=scenarios,
                load_results=load_results,
                recoveries=recoveries,
                ux=ux,
                sources_used=sources_used,
                sources_missing=sources_missing,
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
            context.set("e2e_scenario_testing_report", report)

            _log.info(
                "E2EScenarioTestingEngine finished — verdict=%s scenarios=%d "
                "failed=%d success=%.1f ux=%.1f",
                verdict, len(scenarios), report.failed_count,
                report.success_rate, ux.overall,
            )

            if not passed:
                return self.failed(
                    errors=[
                        f"E2E Scenario Testing failed quality gate "
                        f"(verdict={verdict})"
                    ],
                    outputs={"e2e_scenario_testing_report": report_dict},
                    warnings=[f.message for f in gate_findings],
                )
            return self.ok(
                outputs={"e2e_scenario_testing_report": report_dict},
                metadata={
                    "report_id": report.report_id,
                    "verdict": verdict,
                    "scenario_count": len(scenarios),
                    "failed_count": report.failed_count,
                    "success_rate": report.success_rate,
                    "ux_score": ux.overall,
                    "self_verification_passed": self_ok,
                    "confidence": confidence,
                },
            )
        except Exception as exc:
            _log.exception("E2EScenarioTestingEngine crashed: %s", exc)
            return self.failed(errors=[f"E2EScenarioTestingEngine error: {exc}"])

    def _confidence(self, used, missing, scenarios, ux_overall) -> float:
        total = len(ALL_SOURCES)
        ratio = len(used) / total if total else 0.0
        failed = sum(1 for s in scenarios if getattr(s, "status", "") == "failed")
        penalty = min(0.5, failed * 0.08)
        score_factor = ux_overall / 100.0
        conf = (0.30 * ratio) + (0.40 * score_factor) + 0.30 - penalty
        return round(max(0.0, min(1.0, conf)), 3)


__all__ = ["E2EScenarioTestingEngine"]
