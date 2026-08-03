"""
SelfHealingEngine — Specification 041 (ULTRA CRITICAL)

Collects issues from upstream engines, analyses root causes, plans and
applies safe repairs, re-validates, and retries within limits.
Blocks if critical issues remain or safety constraints would be broken.
"""

from __future__ import annotations

import hashlib
import logging

from ....core.context import GenerationContext
from ....core.result import StageResult
from ...base.base_engine import BaseEngine
from .data_readers import (
    RuntimeReader, StaticReader, ArchitectureReader,
    SecurityReader, PerformanceReader, RefactoringReader,
)
from .report_data import (
    SelfHealingReport, ALL_SOURCES,
    SOURCE_RUNTIME, SOURCE_STATIC, SOURCE_ARCHITECTURE,
    SOURCE_SECURITY, SOURCE_PERFORMANCE, SOURCE_REFACTORING,
)
from .healer import Healer
from .cache_manager import CacheManager
from .quality_gate import QualityGate
from .blueprint_builder import BlueprintBuilder

_log = logging.getLogger("engine.self_healing")


class SelfHealingEngine(BaseEngine):
    """Specification 041 — Intelligent Self-Healing Engine."""

    def __init__(self) -> None:
        super().__init__(
            name="self_healing",
            version="1.0.0",
            description=(
                "Automatically repairs issues found by upstream engines using "
                "root-cause analysis, multi-strategy retries and full re-validation. "
                "Never breaks architecture, logic, security or performance."
            ),
            tags=["self-healing", "repair", "root-cause", "validation", "retry"],
            metadata={"specification": "041", "priority": "ULTRA_CRITICAL"},
        )
        self._runtime_reader = RuntimeReader()
        self._static_reader = StaticReader()
        self._arch_reader = ArchitectureReader()
        self._sec_reader = SecurityReader()
        self._perf_reader = PerformanceReader()
        self._ref_reader = RefactoringReader()
        self._healer = Healer()
        self._cache = CacheManager(enabled=True)
        self._quality_gate = QualityGate()
        self._builder = BlueprintBuilder()

    def execute(self, context: GenerationContext) -> StageResult:
        try:
            _log.info("SelfHealingEngine starting (Spec 041)")

            runtime_data = self._runtime_reader.read(context)
            static_data = self._static_reader.read(context)
            arch_data = self._arch_reader.read(context)
            sec_data = self._sec_reader.read(context)
            perf_data = self._perf_reader.read(context)
            ref_data = self._ref_reader.read(context)

            sources_used = []
            sources_missing = []
            for key, data in (
                (SOURCE_RUNTIME, runtime_data),
                (SOURCE_STATIC, static_data),
                (SOURCE_ARCHITECTURE, arch_data),
                (SOURCE_SECURITY, sec_data),
                (SOURCE_PERFORMANCE, perf_data),
                (SOURCE_REFACTORING, ref_data),
            ):
                if data.available:
                    sources_used.append(key)
                else:
                    sources_missing.append(key)

            cache_payload = str(sorted(sources_used)) + str(
                len(static_data.items or [])
            ) + str(len(runtime_data.items or []))
            cache_key = hashlib.sha256(cache_payload.encode("utf-8")).hexdigest()[:32]

            cached = self._cache.get(cache_key)
            if cached is not None:
                try:
                    report = SelfHealingReport(**{
                        k: v for k, v in cached.items()
                        if k in SelfHealingReport.__dataclass_fields__
                    })
                except Exception:
                    report = None
                if report is not None:
                    report.cache_info = self._cache.info_for_hit(cache_key)
                    context.set("self_healing_report", report)
                    return self.ok(
                        outputs={"self_healing_report": report.to_dict()},
                        metadata={"cache": "hit"},
                    )

            issues, plans, attempts, cycles, all_ok = self._healer.heal(
                runtime_data, static_data, arch_data, sec_data, perf_data, ref_data,
            )

            self_ok = self._healer.self_verify(issues, all_ok)

            confidence = self._confidence(
                sources_used, sources_missing, issues, plans, all_ok,
            )

            report = self._builder.build(
                issues=issues,
                plans=plans,
                attempts=attempts,
                validation_cycles=cycles,
                sources_used=sources_used,
                sources_missing=sources_missing,
                all_validations_passed=all_ok,
                self_verification_passed=self_ok,
                confidence=confidence,
            )

            gate_findings, passed, verdict = self._quality_gate.validate(report)
            report.findings.extend(gate_findings)
            report.verdict = verdict
            report.readiness_status = verdict
            report.self_verification_passed = self_ok
            report.all_validations_passed = all_ok

            report_dict = report.to_dict()
            report.cache_info = self._cache.put(cache_key, report_dict)
            context.set("self_healing_report", report)

            _log.info(
                "SelfHealingEngine finished — verdict=%s issues=%d healed=%d "
                "failed=%d all_ok=%s",
                verdict, len(issues), report.healed_count,
                report.failed_count, all_ok,
            )

            if not passed:
                return self.failed(
                    errors=[
                        f"Self-Healing failed quality gate (verdict={verdict})"
                    ],
                    outputs={"self_healing_report": report_dict},
                    warnings=[f.message for f in gate_findings],
                )
            return self.ok(
                outputs={"self_healing_report": report_dict},
                metadata={
                    "report_id": report.report_id,
                    "verdict": verdict,
                    "issue_count": len(issues),
                    "healed_count": report.healed_count,
                    "failed_count": report.failed_count,
                    "skipped_count": report.skipped_count,
                    "average_confidence": report.average_confidence,
                    "all_validations_passed": all_ok,
                    "self_verification_passed": self_ok,
                    "confidence": confidence,
                },
            )
        except Exception as exc:
            _log.exception("SelfHealingEngine crashed: %s", exc)
            return self.failed(errors=[f"SelfHealingEngine error: {exc}"])

    def _confidence(self, used, missing, issues, plans, all_ok) -> float:
        total = len(ALL_SOURCES)
        ratio = len(used) / total if total else 0.0
        failed = sum(1 for i in issues if getattr(i, "status", "") == "failed")
        penalty = min(0.5, failed * 0.1 + (0.0 if all_ok else 0.25))
        avg_plan = (
            sum(p.confidence for p in plans) / len(plans) if plans else 0.7
        )
        conf = (0.30 * ratio) + (0.40 * avg_plan) + 0.30 - penalty
        return round(max(0.0, min(1.0, conf)), 3)


__all__ = ["SelfHealingEngine"]
