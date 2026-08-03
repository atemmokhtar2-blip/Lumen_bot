"""
ClassGenerationEngine — Specification 031

Intelligent Class Generation Engine.
First engine that emits actual code structure: class skeletons only.
No business logic, no method bodies.
"""

from __future__ import annotations

import logging

from ....core.context import GenerationContext
from ....core.result import StageResult
from ...base.base_engine import BaseEngine
from .data_readers import (
    InitializedProjectReader, ComponentArchitectureReader,
    InterfaceContractReader, CodePlanReader,
    ModuleArchitectureReader, StrategyReader,
)
from .report_data import (
    ClassGenerationReport, ALL_SOURCES,
    SOURCE_INITIALIZED_PROJECT, SOURCE_COMPONENT_ARCHITECTURE,
    SOURCE_INTERFACE_CONTRACT, SOURCE_CODE_PLAN,
    SOURCE_MODULE_ARCHITECTURE, SOURCE_GENERATION_STRATEGY,
)
from .class_skeleton_generator import ClassSkeletonGenerator
from .cache_manager import CacheManager
from .quality_gate import QualityGate
from .blueprint_builder import BlueprintBuilder

_log = logging.getLogger("engine.class_generation")


class ClassGenerationEngine(BaseEngine):
    """Specification 031 — Intelligent Class Generation Engine."""

    def __init__(self) -> None:
        super().__init__(
            name="class_generation",
            version="1.0.0",
            description=(
                "Generates class skeletons (declarations, properties, method "
                "signatures, docs) from components. Never writes business logic "
                "or method bodies."
            ),
            tags=["classes", "skeletons", "di", "no-logic"],
            metadata={"specification": "031", "priority": "CRITICAL"},
        )
        self._project_reader = InitializedProjectReader()
        self._comp_reader = ComponentArchitectureReader()
        self._iface_reader = InterfaceContractReader()
        self._plan_reader = CodePlanReader()
        self._mod_reader = ModuleArchitectureReader()
        self._strategy_reader = StrategyReader()
        self._generator = ClassSkeletonGenerator()
        self._cache = CacheManager(enabled=True)
        self._quality_gate = QualityGate()
        self._builder = BlueprintBuilder()

    def execute(self, context: GenerationContext) -> StageResult:
        try:
            _log.info("ClassGenerationEngine starting (Spec 031)")

            project_data = self._project_reader.read(context)
            comp_data = self._comp_reader.read(context)
            iface_data = self._iface_reader.read(context)
            plan_data = self._plan_reader.read(context)
            mod_data = self._mod_reader.read(context)
            strategy_data = self._strategy_reader.read(context)

            sources_used, sources_missing = [], []
            for name, data in [
                (SOURCE_INITIALIZED_PROJECT, project_data),
                (SOURCE_COMPONENT_ARCHITECTURE, comp_data),
                (SOURCE_INTERFACE_CONTRACT, iface_data),
                (SOURCE_CODE_PLAN, plan_data),
                (SOURCE_MODULE_ARCHITECTURE, mod_data),
                (SOURCE_GENERATION_STRATEGY, strategy_data),
            ]:
                (sources_used if data.available else sources_missing).append(name)

            cache_key = self._cache.make_key(
                project_data.raw, comp_data.raw, iface_data.raw,
                plan_data.raw, mod_data.raw, strategy_data.raw,
            )
            cached = self._cache.get(cache_key)
            if cached is not None:
                report = ClassGenerationReport(**{
                    k: v for k, v in cached.items()
                    if k in ClassGenerationReport.__dataclass_fields__
                })
                report.cache_info = self._cache.info_for_hit(cache_key)
                context.set("class_generation_report", report)
                return self.ok(
                    outputs={"class_generation_report": report.to_dict()},
                    metadata={"cache": "hit"},
                )

            classes, conflicts = self._generator.generate(
                comp_data, iface_data, project_data, plan_data,
            )

            confidence = self._confidence(sources_used, sources_missing, conflicts, classes)

            report = self._builder.build(
                classes=classes,
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
            context.set("class_generation_report", report)

            _log.info(
                "ClassGenerationEngine finished — verdict=%s classes=%d",
                verdict, len(classes),
            )

            if not passed:
                return self.failed(
                    errors=[f"Class Generation failed quality gate (verdict={verdict})"],
                    outputs={"class_generation_report": report_dict},
                    warnings=[f.message for f in gate_findings],
                )
            return self.ok(
                outputs={"class_generation_report": report_dict},
                metadata={
                    "report_id": report.report_id,
                    "verdict": verdict,
                    "class_count": len(classes),
                    "conflict_count": len(conflicts),
                    "confidence": confidence,
                },
            )
        except Exception as exc:
            _log.exception("ClassGenerationEngine crashed: %s", exc)
            return self.failed(errors=[f"ClassGenerationEngine error: {exc}"])

    def _confidence(self, used, missing, conflicts, classes) -> float:
        total = len(ALL_SOURCES)
        ratio = len(used) / total if total else 0.0
        crit = sum(1 for c in conflicts if getattr(c, "severity", "") == "critical")
        penalty = min(0.4, crit * 0.15)
        richness = min(1.0, len(classes) / 8.0)
        conf = (0.5 * ratio) + (0.3 * richness) + 0.2 - penalty
        return round(max(0.0, min(1.0, conf)), 3)


__all__ = ["ClassGenerationEngine"]
