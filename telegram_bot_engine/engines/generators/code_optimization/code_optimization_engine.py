"""
CodeOptimizationEngine — Specification 034 (ULTRA CRITICAL)

Optimises all generated source code after generation.
Never changes behaviour, interfaces, contracts or architecture.
Makes code faster, cleaner, simpler and more maintainable.
"""

from __future__ import annotations

import hashlib
import logging

from ....core.context import GenerationContext
from ....core.result import StageResult
from ...base.base_engine import BaseEngine
from .data_readers import (
    BusinessLogicReader, ClassGenerationReader, FunctionGenerationReader,
    ProjectBuilderReader, ArchitectureDecisionReader, CodePlanReader,
)
from .report_data import (
    CodeOptimizationReport, ALL_SOURCES,
    SOURCE_BUSINESS_LOGIC, SOURCE_CLASS_GENERATION, SOURCE_FUNCTION_GENERATION,
    SOURCE_PROJECT_BUILDER, SOURCE_ARCHITECTURE_DECISION, SOURCE_CODE_PLAN,
)
from .optimizer import CodeOptimizer
from .cache_manager import CacheManager
from .quality_gate import QualityGate
from .blueprint_builder import BlueprintBuilder

_log = logging.getLogger("engine.code_optimization")


class CodeOptimizationEngine(BaseEngine):
    """Specification 034 — Intelligent Code Optimization Engine."""

    def __init__(self) -> None:
        super().__init__(
            name="code_optimization",
            version="1.0.0",
            description=(
                "Optimises generated source: removes dead code, unused imports, "
                "duplicates; reduces complexity; improves readability. "
                "Never changes behaviour, interfaces or architecture."
            ),
            tags=["optimization", "clean-code", "performance", "readability", "regression-safe"],
            metadata={"specification": "034", "priority": "ULTRA_CRITICAL"},
        )
        self._bl_reader = BusinessLogicReader()
        self._class_reader = ClassGenerationReader()
        self._func_reader = FunctionGenerationReader()
        self._project_reader = ProjectBuilderReader()
        self._arch_reader = ArchitectureDecisionReader()
        self._plan_reader = CodePlanReader()
        self._optimizer = CodeOptimizer()
        self._cache = CacheManager(enabled=True)
        self._quality_gate = QualityGate()
        self._builder = BlueprintBuilder()

    def execute(self, context: GenerationContext) -> StageResult:
        try:
            _log.info("CodeOptimizationEngine starting (Spec 034)")

            bl_data = self._bl_reader.read(context)
            class_data = self._class_reader.read(context)
            func_data = self._func_reader.read(context)
            project_data = self._project_reader.read(context)
            arch_data = self._arch_reader.read(context)
            plan_data = self._plan_reader.read(context)

            sources_used = []
            sources_missing = []
            for key, data in (
                (SOURCE_BUSINESS_LOGIC, bl_data),
                (SOURCE_CLASS_GENERATION, class_data),
                (SOURCE_FUNCTION_GENERATION, func_data),
                (SOURCE_PROJECT_BUILDER, project_data),
                (SOURCE_ARCHITECTURE_DECISION, arch_data),
                (SOURCE_CODE_PLAN, plan_data),
            ):
                if data.available:
                    sources_used.append(key)
                else:
                    sources_missing.append(key)

            # Cache key from primary artefact
            cache_payload = ""
            if bl_data.available and bl_data.raw:
                cache_payload = str(sorted(
                    (b.get("method_id", ""), b.get("source_code", "")[:80])
                    for b in (bl_data.items or [])
                ))
            cache_key = hashlib.sha256(cache_payload.encode("utf-8")).hexdigest()[:32] if cache_payload else "empty"

            cached = self._cache.get(cache_key)
            if cached is not None:
                report = CodeOptimizationReport(**{
                    k: v for k, v in cached.items()
                    if k in CodeOptimizationReport.__dataclass_fields__
                }) if isinstance(cached, dict) else None
                if report is not None:
                    report.cache_info = self._cache.info_for_hit(cache_key)
                    context.set("code_optimization_report", report)
                    _log.info("CodeOptimizationEngine cache hit")
                    return self.ok(
                        outputs={"code_optimization_report": report.to_dict()},
                        metadata={"cache": "hit", "report_id": report.report_id},
                    )

            units, actions, issues = self._optimizer.optimize(
                business_data=bl_data,
                class_data=class_data,
                func_data=func_data,
                project_data=project_data,
            )

            confidence = self._confidence(sources_used, sources_missing, issues, units)

            report = self._builder.build(
                units=units,
                actions=actions,
                issues=issues,
                sources_used=sources_used,
                sources_missing=sources_missing,
                confidence=confidence,
            )

            gate_findings, passed, verdict = self._quality_gate.validate(report)
            report.findings.extend(gate_findings)
            report.verdict = verdict
            report.readiness_status = verdict

            report_dict = report.to_dict()
            report.cache_info = self._cache.put(cache_key, report_dict)
            context.set("code_optimization_report", report)

            _log.info(
                "CodeOptimizationEngine finished — verdict=%s units=%d actions=%d lines_saved=%d",
                verdict, len(units), len(actions), report.lines_saved,
            )

            if not passed:
                return self.failed(
                    errors=[f"Code Optimization failed quality gate (verdict={verdict})"],
                    outputs={"code_optimization_report": report_dict},
                    warnings=[f.message for f in gate_findings],
                )
            return self.ok(
                outputs={"code_optimization_report": report_dict},
                metadata={
                    "report_id": report.report_id,
                    "verdict": verdict,
                    "unit_count": len(units),
                    "action_count": len(actions),
                    "lines_saved": report.lines_saved,
                    "average_quality_after": report.average_quality_after,
                    "confidence": confidence,
                },
            )
        except Exception as exc:
            _log.exception("CodeOptimizationEngine crashed: %s", exc)
            return self.failed(errors=[f"CodeOptimizationEngine error: {exc}"])

    def _confidence(self, used, missing, issues, units) -> float:
        total = len(ALL_SOURCES)
        ratio = len(used) / total if total else 0.0
        crit = sum(1 for i in issues if getattr(i, "severity", "") == "critical")
        penalty = min(0.4, crit * 0.15)
        richness = min(1.0, len(units) / 8.0)
        avg_q = (
            sum(u.quality_after for u in units) / len(units) / 100.0
            if units else 0.0
        )
        conf = (0.35 * ratio) + (0.25 * richness) + (0.25 * avg_q) + 0.15 - penalty
        return round(max(0.0, min(1.0, conf)), 3)


__all__ = ["CodeOptimizationEngine"]
