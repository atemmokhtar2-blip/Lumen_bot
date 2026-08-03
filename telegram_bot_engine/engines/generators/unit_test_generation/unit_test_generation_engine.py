"""
UnitTestGenerationEngine — Specification 043 (ULTRA CRITICAL)

Generates professional unit tests for all testable units.
Blocks if any unit lacks tests or any test fails.
"""

from __future__ import annotations

import hashlib
import logging

from ....core.context import GenerationContext
from ....core.result import StageResult
from ...base.base_engine import BaseEngine
from .data_readers import (
    IntegrationReader, SelfHealingReader, ArchitectureReader,
    RefactoringReader, BusinessLogicReader, ProjectContextReader,
)
from .report_data import (
    UnitTestGenerationReport, ALL_SOURCES,
    SOURCE_INTEGRATION, SOURCE_SELF_HEALING, SOURCE_ARCHITECTURE,
    SOURCE_REFACTORING, SOURCE_BUSINESS_LOGIC, SOURCE_PROJECT_CONTEXT,
)
from .generator import UnitTestGenerator
from .cache_manager import CacheManager
from .quality_gate import QualityGate
from .blueprint_builder import BlueprintBuilder

_log = logging.getLogger("engine.unit_test_generation")


class UnitTestGenerationEngine(BaseEngine):
    """Specification 043 — Intelligent Unit Test Generation Engine."""

    def __init__(self) -> None:
        super().__init__(
            name="unit_test_generation",
            version="1.0.0",
            description=(
                "Discovers testable units and generates professional unit tests "
                "(normal/boundary/null/invalid/exception/mock). Blocks if coverage "
                "or pass rate is insufficient."
            ),
            tags=["unit-test", "coverage", "pytest", "mocks", "qa"],
            metadata={"specification": "043", "priority": "ULTRA_CRITICAL"},
        )
        self._integration_reader = IntegrationReader()
        self._heal_reader = SelfHealingReader()
        self._arch_reader = ArchitectureReader()
        self._ref_reader = RefactoringReader()
        self._bl_reader = BusinessLogicReader()
        self._ctx_reader = ProjectContextReader()
        self._generator = UnitTestGenerator()
        self._cache = CacheManager(enabled=True)
        self._quality_gate = QualityGate()
        self._builder = BlueprintBuilder()

    def execute(self, context: GenerationContext) -> StageResult:
        try:
            _log.info("UnitTestGenerationEngine starting (Spec 043)")

            integration_data = self._integration_reader.read(context)
            heal_data = self._heal_reader.read(context)
            arch_data = self._arch_reader.read(context)
            ref_data = self._ref_reader.read(context)
            bl_data = self._bl_reader.read(context)
            ctx_data = self._ctx_reader.read(context)

            sources_used = []
            sources_missing = []
            for key, data in (
                (SOURCE_INTEGRATION, integration_data),
                (SOURCE_SELF_HEALING, heal_data),
                (SOURCE_ARCHITECTURE, arch_data),
                (SOURCE_REFACTORING, ref_data),
                (SOURCE_BUSINESS_LOGIC, bl_data),
                (SOURCE_PROJECT_CONTEXT, ctx_data),
            ):
                if data.available:
                    sources_used.append(key)
                else:
                    sources_missing.append(key)

            primary = ref_data if ref_data.available else bl_data
            cache_payload = str(sorted(sources_used))
            if primary.available and primary.items:
                cache_payload += str(sorted(
                    str(b.get("unit_id") or b.get("name") or "")
                    for b in primary.items
                ))
            cache_key = hashlib.sha256(cache_payload.encode("utf-8")).hexdigest()[:32]

            cached = self._cache.get(cache_key)
            if cached is not None:
                try:
                    report = UnitTestGenerationReport(**{
                        k: v for k, v in cached.items()
                        if k in UnitTestGenerationReport.__dataclass_fields__
                    })
                except Exception:
                    report = None
                if report is not None:
                    report.cache_info = self._cache.info_for_hit(cache_key)
                    context.set("unit_test_generation_report", report)
                    return self.ok(
                        outputs={"unit_test_generation_report": report.to_dict()},
                        metadata={"cache": "hit"},
                    )

            tests, gaps, failures, coverage, all_passed = self._generator.generate(
                integration_data, heal_data, arch_data, ref_data, bl_data,
            )

            self_ok = self._generator.self_verify(tests, all_passed)

            confidence = self._confidence(
                sources_used, sources_missing, tests, coverage.overall, all_passed,
            )

            report = self._builder.build(
                tests=tests,
                gaps=gaps,
                failures=failures,
                coverage=coverage,
                sources_used=sources_used,
                sources_missing=sources_missing,
                all_tests_passed=all_passed,
                self_verification_passed=self_ok,
                confidence=confidence,
            )

            gate_findings, passed, verdict = self._quality_gate.validate(report)
            report.findings.extend(gate_findings)
            report.verdict = verdict
            report.readiness_status = verdict
            report.self_verification_passed = self_ok
            report.all_tests_passed = all_passed

            report_dict = report.to_dict()
            report.cache_info = self._cache.put(cache_key, report_dict)
            context.set("unit_test_generation_report", report)

            _log.info(
                "UnitTestGenerationEngine finished — verdict=%s tests=%d "
                "cases=%d cov=%.1f all_passed=%s",
                verdict, len(tests), report.case_count, coverage.overall, all_passed,
            )

            if not passed:
                return self.failed(
                    errors=[
                        f"Unit Test Generation failed quality gate "
                        f"(verdict={verdict})"
                    ],
                    outputs={"unit_test_generation_report": report_dict},
                    warnings=[f.message for f in gate_findings],
                )
            return self.ok(
                outputs={"unit_test_generation_report": report_dict},
                metadata={
                    "report_id": report.report_id,
                    "verdict": verdict,
                    "test_count": len(tests),
                    "case_count": report.case_count,
                    "gap_count": report.gap_count,
                    "failure_count": report.failure_count,
                    "coverage_overall": coverage.overall,
                    "all_tests_passed": all_passed,
                    "self_verification_passed": self_ok,
                    "confidence": confidence,
                },
            )
        except Exception as exc:
            _log.exception("UnitTestGenerationEngine crashed: %s", exc)
            return self.failed(errors=[f"UnitTestGenerationEngine error: {exc}"])

    def _confidence(self, used, missing, tests, overall, all_passed) -> float:
        total = len(ALL_SOURCES)
        ratio = len(used) / total if total else 0.0
        richness = min(1.0, len(tests) / 10.0)
        score_factor = overall / 100.0
        penalty = 0.0 if all_passed else 0.25
        conf = (0.25 * ratio) + (0.25 * richness) + (0.35 * score_factor) + 0.15 - penalty
        return round(max(0.0, min(1.0, conf)), 3)


__all__ = ["UnitTestGenerationEngine"]
