"""
FunctionGenerationEngine — Specification 032

Intelligent Function Generation Engine.
Builds full method/function signatures for every class.
No business logic, no method bodies.
"""

from __future__ import annotations

import logging

from ....core.context import GenerationContext
from ....core.result import StageResult
from ...base.base_engine import BaseEngine
from .data_readers import (
    ClassGenerationReader, ComponentArchitectureReader,
    InterfaceContractReader, CodePlanReader, ModuleArchitectureReader,
)
from .report_data import (
    FunctionGenerationReport, ALL_SOURCES,
    SOURCE_CLASS_GENERATION, SOURCE_COMPONENT_ARCHITECTURE,
    SOURCE_INTERFACE_CONTRACT, SOURCE_CODE_PLAN, SOURCE_MODULE_ARCHITECTURE,
)
from .method_skeleton_generator import MethodSkeletonGenerator
from .cache_manager import CacheManager
from .quality_gate import QualityGate
from .blueprint_builder import BlueprintBuilder

_log = logging.getLogger("engine.function_generation")


class FunctionGenerationEngine(BaseEngine):
    """Specification 032 — Intelligent Function Generation Engine."""

    def __init__(self) -> None:
        super().__init__(
            name="function_generation",
            version="1.0.0",
            description=(
                "Generates method/function signatures, constructors and abstract "
                "methods for every class. Never writes business logic or bodies."
            ),
            tags=["functions", "methods", "signatures", "no-logic"],
            metadata={"specification": "032", "priority": "CRITICAL"},
        )
        self._class_reader = ClassGenerationReader()
        self._comp_reader = ComponentArchitectureReader()
        self._iface_reader = InterfaceContractReader()
        self._plan_reader = CodePlanReader()
        self._mod_reader = ModuleArchitectureReader()
        self._generator = MethodSkeletonGenerator()
        self._cache = CacheManager(enabled=True)
        self._quality_gate = QualityGate()
        self._builder = BlueprintBuilder()

    def execute(self, context: GenerationContext) -> StageResult:
        try:
            _log.info("FunctionGenerationEngine starting (Spec 032)")

            class_data = self._class_reader.read(context)
            comp_data = self._comp_reader.read(context)
            iface_data = self._iface_reader.read(context)
            plan_data = self._plan_reader.read(context)
            mod_data = self._mod_reader.read(context)

            sources_used, sources_missing = [], []
            for name, data in [
                (SOURCE_CLASS_GENERATION, class_data),
                (SOURCE_COMPONENT_ARCHITECTURE, comp_data),
                (SOURCE_INTERFACE_CONTRACT, iface_data),
                (SOURCE_CODE_PLAN, plan_data),
                (SOURCE_MODULE_ARCHITECTURE, mod_data),
            ]:
                (sources_used if data.available else sources_missing).append(name)

            cache_key = self._cache.make_key(
                class_data.raw, comp_data.raw, iface_data.raw,
                plan_data.raw, mod_data.raw,
            )
            cached = self._cache.get(cache_key)
            if cached is not None:
                report = FunctionGenerationReport(**{
                    k: v for k, v in cached.items()
                    if k in FunctionGenerationReport.__dataclass_fields__
                })
                report.cache_info = self._cache.info_for_hit(cache_key)
                context.set("function_generation_report", report)
                return self.ok(
                    outputs={"function_generation_report": report.to_dict()},
                    metadata={"cache": "hit"},
                )

            methods, registry, conflicts = self._generator.generate(
                class_data, iface_data, comp_data,
            )

            confidence = self._confidence(sources_used, sources_missing, conflicts, methods)

            report = self._builder.build(
                methods=methods,
                method_registry=registry,
                conflicts=conflicts,
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
            context.set("function_generation_report", report)

            _log.info(
                "FunctionGenerationEngine finished — verdict=%s methods=%d",
                verdict, len(methods),
            )

            if not passed:
                return self.failed(
                    errors=[f"Function Generation failed quality gate (verdict={verdict})"],
                    outputs={"function_generation_report": report_dict},
                    warnings=[f.message for f in gate_findings],
                )
            return self.ok(
                outputs={"function_generation_report": report_dict},
                metadata={
                    "report_id": report.report_id,
                    "verdict": verdict,
                    "method_count": len(methods),
                    "class_count": len(registry),
                    "conflict_count": len(conflicts),
                    "confidence": confidence,
                },
            )
        except Exception as exc:
            _log.exception("FunctionGenerationEngine crashed: %s", exc)
            return self.failed(errors=[f"FunctionGenerationEngine error: {exc}"])

    def _confidence(self, used, missing, conflicts, methods) -> float:
        total = len(ALL_SOURCES)
        ratio = len(used) / total if total else 0.0
        crit = sum(1 for c in conflicts if getattr(c, "severity", "") == "critical")
        penalty = min(0.4, crit * 0.15)
        richness = min(1.0, len(methods) / 10.0)
        conf = (0.5 * ratio) + (0.3 * richness) + 0.2 - penalty
        return round(max(0.0, min(1.0, conf)), 3)


__all__ = ["FunctionGenerationEngine"]
