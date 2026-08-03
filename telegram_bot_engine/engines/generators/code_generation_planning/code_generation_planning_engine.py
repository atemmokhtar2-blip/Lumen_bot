"""
CodeGenerationPlanningEngine — Specification 029 v2.0

Intelligent Code Generation Planning Engine.
Last planning step before any code is written. Builds a complete intelligent
plan (context, units, adaptive queue, rules, style, simulation, rollback, score).
"""

from __future__ import annotations

import logging

from ....core.context import GenerationContext
from ....core.result import StageResult
from ...base.base_engine import BaseEngine
from .data_readers import (
    ReadinessReader, ExecutionPlanReader, StructureReader,
    ModuleArchitectureReader, ComponentArchitectureReader,
    InterfaceContractReader, ResourceDependencyReader,
    StrategyReader, SessionReader,
)
from .report_data import (
    IntelligentCodeGenerationPlan, ALL_SOURCES,
    SOURCE_READINESS, SOURCE_EXECUTION_PLAN, SOURCE_PROJECT_STRUCTURE,
    SOURCE_MODULE_ARCHITECTURE, SOURCE_COMPONENT_ARCHITECTURE,
    SOURCE_INTERFACE_CONTRACT, SOURCE_RESOURCE_DEPENDENCY,
    SOURCE_GENERATION_STRATEGY, SOURCE_SESSION,
)
from .intelligent_planner import IntelligentPlanner
from .cache_manager import CacheManager
from .quality_gate import QualityGate
from .blueprint_builder import BlueprintBuilder

_log = logging.getLogger("engine.code_generation_planning")


class CodeGenerationPlanningEngine(BaseEngine):
    """Specification 029 v2.0 — Intelligent Code Generation Planning Engine."""

    def __init__(self) -> None:
        super().__init__(
            name="code_generation_planning",
            version="2.0.0",
            description=(
                "Builds a complete intelligent code-generation plan: context, "
                "units, adaptive queue, SOLID/Clean rules, style, dry simulation, "
                "rollback points and intelligence score. Does not write code."
            ),
            tags=["code-plan", "intelligent", "queue", "simulation", "rules"],
            metadata={"specification": "029", "version": "2.0", "priority": "CRITICAL"},
        )
        self._readiness_reader = ReadinessReader()
        self._exec_reader = ExecutionPlanReader()
        self._struct_reader = StructureReader()
        self._mod_reader = ModuleArchitectureReader()
        self._comp_reader = ComponentArchitectureReader()
        self._iface_reader = InterfaceContractReader()
        self._res_reader = ResourceDependencyReader()
        self._strategy_reader = StrategyReader()
        self._session_reader = SessionReader()
        self._planner = IntelligentPlanner()
        self._cache = CacheManager(enabled=True)
        self._quality_gate = QualityGate()
        self._builder = BlueprintBuilder()

    def execute(self, context: GenerationContext) -> StageResult:
        try:
            _log.info("CodeGenerationPlanningEngine starting (Spec 029 v2.0)")

            readiness_data = self._readiness_reader.read(context)
            exec_data = self._exec_reader.read(context)
            struct_data = self._struct_reader.read(context)
            mod_data = self._mod_reader.read(context)
            comp_data = self._comp_reader.read(context)
            iface_data = self._iface_reader.read(context)
            res_data = self._res_reader.read(context)
            strategy_data = self._strategy_reader.read(context)
            session_data = self._session_reader.read(context)

            sources_used, sources_missing = [], []
            for name, data in [
                (SOURCE_READINESS, readiness_data),
                (SOURCE_EXECUTION_PLAN, exec_data),
                (SOURCE_PROJECT_STRUCTURE, struct_data),
                (SOURCE_MODULE_ARCHITECTURE, mod_data),
                (SOURCE_COMPONENT_ARCHITECTURE, comp_data),
                (SOURCE_INTERFACE_CONTRACT, iface_data),
                (SOURCE_RESOURCE_DEPENDENCY, res_data),
                (SOURCE_GENERATION_STRATEGY, strategy_data),
                (SOURCE_SESSION, session_data),
            ]:
                (sources_used if data.available else sources_missing).append(name)

            cache_key = self._cache.make_key(
                readiness_data.raw, exec_data.raw, struct_data.raw,
                mod_data.raw, comp_data.raw, iface_data.raw,
                res_data.raw, strategy_data.raw, session_data.raw,
            )
            cached = self._cache.get(cache_key)
            if cached is not None:
                plan = IntelligentCodeGenerationPlan(**{
                    k: v for k, v in cached.items()
                    if k in IntelligentCodeGenerationPlan.__dataclass_fields__
                })
                plan.cache_info = self._cache.info_for_hit(cache_key)
                context.set("code_generation_plan", plan)
                return self.ok(
                    outputs={"code_generation_plan": plan.to_dict()},
                    metadata={"cache": "hit"},
                )

            (
                gen_ctx, units, queue, gen_order, rules, style,
                simulation, rollbacks, scores, overall, conflicts,
            ) = self._planner.plan(
                strategy_data, struct_data, mod_data, comp_data,
                iface_data, res_data, session_data,
            )

            confidence = self._confidence(sources_used, sources_missing, conflicts, units, simulation.passed)

            plan = self._builder.build(
                context=gen_ctx,
                units=units,
                queue=queue,
                generation_order=gen_order,
                rules=rules,
                style=style,
                simulation=simulation,
                rollback_points=rollbacks,
                intelligence_scores=scores,
                overall_score=overall,
                conflicts=conflicts,
                sources_used=sources_used,
                sources_missing=sources_missing,
                confidence=confidence,
            )

            gate_findings, passed, verdict = self._quality_gate.validate(plan)
            plan.findings.extend(gate_findings)
            plan.verdict = verdict
            plan.readiness_status = verdict

            plan_dict = plan.to_dict()
            plan.cache_info = self._cache.put(cache_key, plan_dict)
            context.set("code_generation_plan", plan)

            _log.info(
                "CodeGenerationPlanningEngine finished — verdict=%s units=%d score=%.1f",
                verdict, len(units), overall,
            )

            if not passed:
                return self.failed(
                    errors=[f"Code Generation Plan failed quality gate (verdict={verdict})"],
                    outputs={"code_generation_plan": plan_dict},
                    warnings=[f.message for f in gate_findings],
                )
            return self.ok(
                outputs={"code_generation_plan": plan_dict},
                metadata={
                    "plan_id": plan.plan_id,
                    "verdict": verdict,
                    "unit_count": len(units),
                    "queue_length": len(queue),
                    "intelligence_score": overall,
                    "simulation_passed": simulation.passed,
                    "conflict_count": len(conflicts),
                    "confidence": confidence,
                },
            )
        except Exception as exc:
            _log.exception("CodeGenerationPlanningEngine crashed: %s", exc)
            return self.failed(errors=[f"CodeGenerationPlanningEngine error: {exc}"])

    def _confidence(self, used, missing, conflicts, units, sim_ok) -> float:
        total = len(ALL_SOURCES)
        ratio = len(used) / total if total else 0.0
        crit = sum(1 for c in conflicts if getattr(c, "severity", "") == "critical")
        penalty = min(0.4, crit * 0.12)
        richness = min(1.0, len(units) / 10.0)
        sim_bonus = 0.1 if sim_ok else 0.0
        conf = (0.45 * ratio) + (0.25 * richness) + 0.2 + sim_bonus - penalty
        return round(max(0.0, min(1.0, conf)), 3)


__all__ = ["CodeGenerationPlanningEngine"]
