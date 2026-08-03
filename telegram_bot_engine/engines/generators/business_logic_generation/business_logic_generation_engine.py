"""
BusinessLogicGenerationEngine — Specification 033 (ULTRA CRITICAL)

Writes production-grade business logic for every method skeleton.
Enforces Clean Code, SOLID, security, performance and self-review.
"""

from __future__ import annotations

import logging

from ....core.context import GenerationContext
from ....core.result import StageResult
from ...base.base_engine import BaseEngine
from .data_readers import (
    ClassGenerationReader, FunctionGenerationReader,
    ComponentArchitectureReader, InterfaceContractReader,
    CodePlanReader, ModuleArchitectureReader,
)
from .report_data import (
    BusinessLogicReport, ALL_SOURCES,
    SOURCE_CLASS_GENERATION, SOURCE_FUNCTION_GENERATION,
    SOURCE_COMPONENT_ARCHITECTURE, SOURCE_INTERFACE_CONTRACT,
    SOURCE_CODE_PLAN, SOURCE_MODULE_ARCHITECTURE,
)
from .logic_builder import LogicBuilder
from .cache_manager import CacheManager
from .quality_gate import QualityGate
from .blueprint_builder import BlueprintBuilder

_log = logging.getLogger("engine.business_logic_generation")


class BusinessLogicGenerationEngine(BaseEngine):
    """Specification 033 — Intelligent Business Logic Generation Engine."""

    def __init__(self) -> None:
        super().__init__(
            name="business_logic_generation",
            version="1.0.0",
            description=(
                "Emits production-grade business logic bodies for every method. "
                "Enforces Clean Code, SOLID, security, error handling and self-review."
            ),
            tags=["business-logic", "clean-code", "solid", "security"],
            metadata={"specification": "033", "priority": "ULTRA_CRITICAL"},
        )
        self._class_reader = ClassGenerationReader()
        self._func_reader = FunctionGenerationReader()
        self._comp_reader = ComponentArchitectureReader()
        self._iface_reader = InterfaceContractReader()
        self._plan_reader = CodePlanReader()
        self._mod_reader = ModuleArchitectureReader()
        self._builder_logic = LogicBuilder()
        self._cache = CacheManager(enabled=True)
        self._quality_gate = QualityGate()
        self._builder = BlueprintBuilder()

    def execute(self, context: GenerationContext) -> StageResult:
        try:
            _log.info("BusinessLogicGenerationEngine starting (Spec 033)")

            class_data = self._class_reader.read(context)
            func_data = self._func_reader.read(context)
            comp_data = self._comp_reader.read(context)
            iface_data = self._iface_reader.read(context)
            plan_data = self._plan_reader.read(context)
            mod_data = self._mod_reader.read(context)

            sources_used, sources_missing = [], []
            for name, data in [
                (SOURCE_CLASS_GENERATION, class_data),
                (SOURCE_FUNCTION_GENERATION, func_data),
                (SOURCE_COMPONENT_ARCHITECTURE, comp_data),
                (SOURCE_INTERFACE_CONTRACT, iface_data),
                (SOURCE_CODE_PLAN, plan_data),
                (SOURCE_MODULE_ARCHITECTURE, mod_data),
            ]:
                (sources_used if data.available else sources_missing).append(name)

            cache_key = self._cache.make_key(
                class_data.raw, func_data.raw, comp_data.raw,
                iface_data.raw, plan_data.raw, mod_data.raw,
            )
            cached = self._cache.get(cache_key)
            if cached is not None:
                report = BusinessLogicReport(**{
                    k: v for k, v in cached.items()
                    if k in BusinessLogicReport.__dataclass_fields__
                })
                report.cache_info = self._cache.info_for_hit(cache_key)
                context.set("business_logic_report", report)
                return self.ok(
                    outputs={"business_logic_report": report.to_dict()},
                    metadata={"cache": "hit"},
                )

            bodies, issues, opts = self._builder_logic.build(
                class_data, func_data, comp_data,
            )

            confidence = self._confidence(sources_used, sources_missing, issues, bodies)

            report = self._builder.build(
                bodies=bodies,
                issues=issues,
                optimizations=opts,
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
            context.set("business_logic_report", report)

            _log.info(
                "BusinessLogicGenerationEngine finished — verdict=%s bodies=%d avg=%.1f",
                verdict, len(bodies), report.average_quality,
            )

            if not passed:
                return self.failed(
                    errors=[f"Business Logic failed quality gate (verdict={verdict})"],
                    outputs={"business_logic_report": report_dict},
                    warnings=[f.message for f in gate_findings],
                )
            return self.ok(
                outputs={"business_logic_report": report_dict},
                metadata={
                    "report_id": report.report_id,
                    "verdict": verdict,
                    "body_count": len(bodies),
                    "average_quality": report.average_quality,
                    "issue_count": len(issues),
                    "optimization_count": len(opts),
                    "confidence": confidence,
                },
            )
        except Exception as exc:
            _log.exception("BusinessLogicGenerationEngine crashed: %s", exc)
            return self.failed(errors=[f"BusinessLogicGenerationEngine error: {exc}"])

    def _confidence(self, used, missing, issues, bodies) -> float:
        total = len(ALL_SOURCES)
        ratio = len(used) / total if total else 0.0
        crit = sum(1 for i in issues if getattr(i, "severity", "") == "critical")
        penalty = min(0.4, crit * 0.15)
        richness = min(1.0, len(bodies) / 8.0)
        avg_q = (sum(b.quality_score for b in bodies) / len(bodies) / 100.0) if bodies else 0.0
        conf = (0.35 * ratio) + (0.25 * richness) + (0.25 * avg_q) + 0.15 - penalty
        return round(max(0.0, min(1.0, conf)), 3)


__all__ = ["BusinessLogicGenerationEngine"]
