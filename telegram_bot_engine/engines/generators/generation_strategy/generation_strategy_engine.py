"""
GenerationStrategyEngine — Specification 026

Builds the complete strategy for generating the project before any file is written.
Produces the Generation Strategy Blueprint.
"""

from __future__ import annotations

import logging

from ....core.context import GenerationContext
from ....core.result import StageResult
from ...base.base_engine import BaseEngine
from .data_readers import (
    ExecutionPlanReader, ProjectStructureReader, ModuleArchitectureReader,
    ComponentArchitectureReader, InterfaceContractReader, DataFlowReader,
    ResourceDependencyReader,
)
from .report_data import (
    GenerationStrategyBlueprint, ALL_SOURCES,
    SOURCE_EXECUTION_PLAN, SOURCE_PROJECT_STRUCTURE, SOURCE_MODULE_ARCHITECTURE,
    SOURCE_COMPONENT_ARCHITECTURE, SOURCE_INTERFACE_CONTRACT, SOURCE_DATA_FLOW,
    SOURCE_RESOURCE_DEPENDENCY,
)
from .strategy_planner import StrategyPlanner
from .strategy_validator import StrategyValidator
from .cache_manager import CacheManager
from .quality_gate import QualityGate
from .blueprint_builder import BlueprintBuilder

_log = logging.getLogger("engine.generation_strategy")


class GenerationStrategyEngine(BaseEngine):
    """Specification 026 — Generation Strategy Engine."""

    def __init__(self) -> None:
        super().__init__(
            name="generation_strategy",
            version="1.0.0",
            description=(
                "Builds the complete ordered strategy for generating the "
                "project (stages, items, rules, rollback, optimisations) "
                "before any file is written."
            ),
            tags=["generation", "strategy", "order", "stages"],
            metadata={"specification": "026", "priority": "CRITICAL"},
        )
        self._exec_reader = ExecutionPlanReader()
        self._struct_reader = ProjectStructureReader()
        self._mod_reader = ModuleArchitectureReader()
        self._comp_reader = ComponentArchitectureReader()
        self._iface_reader = InterfaceContractReader()
        self._flow_reader = DataFlowReader()
        self._res_reader = ResourceDependencyReader()
        self._planner = StrategyPlanner()
        self._validator = StrategyValidator()
        self._cache = CacheManager(enabled=True)
        self._quality_gate = QualityGate()
        self._builder = BlueprintBuilder()

    def execute(self, context: GenerationContext) -> StageResult:
        try:
            _log.info("GenerationStrategyEngine starting (Spec 026)")

            exec_data = self._exec_reader.read(context)
            struct_data = self._struct_reader.read(context)
            mod_data = self._mod_reader.read(context)
            comp_data = self._comp_reader.read(context)
            iface_data = self._iface_reader.read(context)
            flow_data = self._flow_reader.read(context)
            res_data = self._res_reader.read(context)

            sources_used, sources_missing = [], []
            for name, data in [
                (SOURCE_EXECUTION_PLAN, exec_data),
                (SOURCE_PROJECT_STRUCTURE, struct_data),
                (SOURCE_MODULE_ARCHITECTURE, mod_data),
                (SOURCE_COMPONENT_ARCHITECTURE, comp_data),
                (SOURCE_INTERFACE_CONTRACT, iface_data),
                (SOURCE_DATA_FLOW, flow_data),
                (SOURCE_RESOURCE_DEPENDENCY, res_data),
            ]:
                (sources_used if data.available else sources_missing).append(name)

            cache_key = self._cache.make_key(
                exec_data.raw, struct_data.raw, mod_data.raw, comp_data.raw,
                iface_data.raw, flow_data.raw, res_data.raw,
            )
            cached = self._cache.get(cache_key)
            if cached is not None:
                bp = GenerationStrategyBlueprint(**{
                    k: v for k, v in cached.items()
                    if k in GenerationStrategyBlueprint.__dataclass_fields__
                })
                bp.cache_info = self._cache.info_for_hit(cache_key)
                context.set("generation_strategy_blueprint", bp)
                return self.ok(
                    outputs={"generation_strategy_blueprint": bp.to_dict()},
                    metadata={"cache": "hit"},
                )

            stages, items, gen_order, rules, rollbacks, opts = self._planner.plan(
                struct_data, mod_data, comp_data, res_data,
            )
            conflicts = self._validator.validate(stages, items, gen_order)

            confidence = self._confidence(sources_used, sources_missing, conflicts, items)

            bp = self._builder.build(
                stages=stages,
                items=items,
                generation_order=gen_order,
                rules=rules,
                rollback_points=rollbacks,
                optimizations=opts,
                conflicts=conflicts,
                sources_used=sources_used,
                sources_missing=sources_missing,
                confidence=confidence,
            )

            gate_findings, passed, verdict = self._quality_gate.validate(bp)
            bp.findings.extend(gate_findings)
            bp.verdict = verdict
            bp.readiness_status = verdict

            bp_dict = bp.to_dict()
            bp.cache_info = self._cache.put(cache_key, bp_dict)
            context.set("generation_strategy_blueprint", bp)

            _log.info(
                "GenerationStrategyEngine finished — verdict=%s stages=%d items=%d",
                verdict, len(stages), len(items),
            )

            if not passed:
                return self.failed(
                    errors=[f"Generation Strategy failed quality gate (verdict={verdict})"],
                    outputs={"generation_strategy_blueprint": bp_dict},
                    warnings=[f.message for f in gate_findings],
                )
            return self.ok(
                outputs={"generation_strategy_blueprint": bp_dict},
                metadata={
                    "blueprint_id": bp.blueprint_id,
                    "verdict": verdict,
                    "stage_count": len(stages),
                    "item_count": len(items),
                    "conflict_count": len(conflicts),
                    "confidence": confidence,
                },
            )
        except Exception as exc:
            _log.exception("GenerationStrategyEngine crashed: %s", exc)
            return self.failed(errors=[f"GenerationStrategyEngine error: {exc}"])

    def _confidence(self, used, missing, conflicts, items) -> float:
        total = len(ALL_SOURCES)
        ratio = len(used) / total if total else 0.0
        crit = sum(1 for c in conflicts if getattr(c, "severity", "") == "critical")
        penalty = min(0.4, crit * 0.15)
        richness = min(1.0, len(items) / 12.0)
        conf = (0.5 * ratio) + (0.3 * richness) + 0.2 - penalty
        return round(max(0.0, min(1.0, conf)), 3)


__all__ = ["GenerationStrategyEngine"]
