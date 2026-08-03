"""
PerformanceOptimizationEngine — Specification 036 (ULTRA CRITICAL)

Reviews project performance, detects bottlenecks, applies safe optimisations,
and blocks progression when critical bottlenecks remain.
"""

from __future__ import annotations

import hashlib
import logging

from ....core.context import GenerationContext
from ....core.result import StageResult
from ...base.base_engine import BaseEngine
from .data_readers import (
    SecurityReviewReader, CodeOptimizationReader, BusinessLogicReader,
    ArchitectureDecisionReader, ProjectContextReader, CodePlanReader,
)
from .report_data import (
    PerformanceReport, ALL_SOURCES,
    SOURCE_SECURITY_REVIEW, SOURCE_CODE_OPTIMIZATION, SOURCE_BUSINESS_LOGIC,
    SOURCE_ARCHITECTURE_DECISION, SOURCE_PROJECT_CONTEXT, SOURCE_CODE_PLAN,
)
from .performance_analyzer import PerformanceAnalyzer
from .cache_manager import CacheManager
from .quality_gate import QualityGate
from .blueprint_builder import BlueprintBuilder

_log = logging.getLogger("engine.performance_optimization")


class PerformanceOptimizationEngine(BaseEngine):
    """Specification 036 — Intelligent Performance Optimization Engine."""

    def __init__(self) -> None:
        super().__init__(
            name="performance_optimization",
            version="1.0.0",
            description=(
                "Analyses CPU, memory, algorithms, DB, API and Telegram paths; "
                "applies safe performance optimisations without changing behaviour."
            ),
            tags=["performance", "optimization", "latency", "throughput", "cache"],
            metadata={"specification": "036", "priority": "ULTRA_CRITICAL"},
        )
        self._sec_reader = SecurityReviewReader()
        self._opt_reader = CodeOptimizationReader()
        self._bl_reader = BusinessLogicReader()
        self._arch_reader = ArchitectureDecisionReader()
        self._ctx_reader = ProjectContextReader()
        self._plan_reader = CodePlanReader()
        self._analyzer = PerformanceAnalyzer()
        self._cache = CacheManager(enabled=True)
        self._quality_gate = QualityGate()
        self._builder = BlueprintBuilder()

    def execute(self, context: GenerationContext) -> StageResult:
        try:
            _log.info("PerformanceOptimizationEngine starting (Spec 036)")

            sec_data = self._sec_reader.read(context)
            opt_data = self._opt_reader.read(context)
            bl_data = self._bl_reader.read(context)
            arch_data = self._arch_reader.read(context)
            ctx_data = self._ctx_reader.read(context)
            plan_data = self._plan_reader.read(context)

            sources_used = []
            sources_missing = []
            for key, data in (
                (SOURCE_SECURITY_REVIEW, sec_data),
                (SOURCE_CODE_OPTIMIZATION, opt_data),
                (SOURCE_BUSINESS_LOGIC, bl_data),
                (SOURCE_ARCHITECTURE_DECISION, arch_data),
                (SOURCE_PROJECT_CONTEXT, ctx_data),
                (SOURCE_CODE_PLAN, plan_data),
            ):
                if data.available:
                    sources_used.append(key)
                else:
                    sources_missing.append(key)

            primary = sec_data if sec_data.available else (
                opt_data if opt_data.available else bl_data
            )
            cache_payload = ""
            if primary.available and primary.items:
                cache_payload = str(sorted(
                    (
                        str(b.get("unit_id") or b.get("method_id") or ""),
                        str(
                            b.get("secured_code")
                            or b.get("optimized_code")
                            or b.get("source_code")
                            or ""
                        )[:80],
                    )
                    for b in primary.items
                ))
            cache_key = (
                hashlib.sha256(cache_payload.encode("utf-8")).hexdigest()[:32]
                if cache_payload else "empty"
            )

            cached = self._cache.get(cache_key)
            if cached is not None:
                try:
                    report = PerformanceReport(**{
                        k: v for k, v in cached.items()
                        if k in PerformanceReport.__dataclass_fields__
                    })
                except Exception:
                    report = None
                if report is not None:
                    report.cache_info = self._cache.info_for_hit(cache_key)
                    context.set("performance_optimization_report", report)
                    return self.ok(
                        outputs={"performance_optimization_report": report.to_dict()},
                        metadata={"cache": "hit"},
                    )

            units, bottlenecks, actions, simulations, cache_plans = (
                self._analyzer.analyze_and_optimize(sec_data, opt_data, bl_data)
            )

            self_ok, residual = self._analyzer.self_review(units, bottlenecks)
            if residual:
                bottlenecks.extend(residual)

            confidence = self._confidence(
                sources_used, sources_missing, bottlenecks, units, actions,
            )

            report = self._builder.build(
                units=units,
                bottlenecks=bottlenecks,
                actions=actions,
                simulations=simulations,
                cache_plans=cache_plans,
                sources_used=sources_used,
                sources_missing=sources_missing,
                self_review_passed=self_ok,
                confidence=confidence,
            )

            gate_findings, passed, verdict = self._quality_gate.validate(report)
            report.findings.extend(gate_findings)
            report.verdict = verdict
            report.readiness_status = verdict
            report.self_review_passed = self_ok

            report_dict = report.to_dict()
            report.cache_info = self._cache.put(cache_key, report_dict)
            context.set("performance_optimization_report", report)

            _log.info(
                "PerformanceOptimizationEngine finished — verdict=%s units=%d "
                "bottlenecks=%d actions=%d open_crit=%d self_review=%s",
                verdict, len(units), len(bottlenecks), len(actions),
                report.open_critical_count, self_ok,
            )

            if not passed:
                return self.failed(
                    errors=[
                        f"Performance Optimization failed quality gate "
                        f"(verdict={verdict})"
                    ],
                    outputs={"performance_optimization_report": report_dict},
                    warnings=[f.message for f in gate_findings],
                )
            return self.ok(
                outputs={"performance_optimization_report": report_dict},
                metadata={
                    "report_id": report.report_id,
                    "verdict": verdict,
                    "unit_count": len(units),
                    "bottleneck_count": len(bottlenecks),
                    "action_count": len(actions),
                    "open_critical_count": report.open_critical_count,
                    "self_review_passed": self_ok,
                    "confidence": confidence,
                },
            )
        except Exception as exc:
            _log.exception("PerformanceOptimizationEngine crashed: %s", exc)
            return self.failed(
                errors=[f"PerformanceOptimizationEngine error: {exc}"]
            )

    def _confidence(self, used, missing, bottlenecks, units, actions) -> float:
        total = len(ALL_SOURCES)
        ratio = len(used) / total if total else 0.0
        open_crit = sum(
            1 for b in bottlenecks
            if getattr(b, "severity", "") == "critical"
            and getattr(b, "status", "") == "open"
        )
        penalty = min(0.5, open_crit * 0.2)
        richness = min(1.0, len(units) / 8.0)
        action_bonus = min(0.2, len(actions) * 0.02)
        conf = (0.30 * ratio) + (0.25 * richness) + action_bonus + 0.25 - penalty
        return round(max(0.0, min(1.0, conf)), 3)


__all__ = ["PerformanceOptimizationEngine"]
