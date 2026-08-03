"""
DataFlowPlanningEngine — Specification 024

Designs all data movement paths before generation.
Produces the Data Flow Blueprint.
"""

from __future__ import annotations

import logging
from typing import List

from ....core.context import GenerationContext
from ....core.result import StageResult
from ...base.base_engine import BaseEngine
from .data_readers import (
    ExecutionPlanReader, ProjectStructureReader, ModuleArchitectureReader,
    ComponentArchitectureReader, InterfaceContractReader, RequirementNormalizationReader,
)
from .report_data import (
    DataFlowBlueprint, ALL_SOURCES,
    SOURCE_EXECUTION_PLAN, SOURCE_PROJECT_STRUCTURE, SOURCE_MODULE_ARCHITECTURE,
    SOURCE_COMPONENT_ARCHITECTURE, SOURCE_INTERFACE_CONTRACT, SOURCE_NORMALIZED_REQUIREMENTS,
)
from .flow_mapper import FlowMapper
from .flow_validator import FlowValidator
from .cache_manager import CacheManager
from .quality_gate import QualityGate
from .blueprint_builder import BlueprintBuilder

_log = logging.getLogger("engine.data_flow_planning")


class DataFlowPlanningEngine(BaseEngine):
    """Specification 024 — Data Flow Planning Engine."""

    def __init__(self) -> None:
        super().__init__(
            name="data_flow_planning",
            version="1.0.0",
            description=(
                "Designs all data movement paths, transformations, "
                "validation and security rules before generation."
            ),
            tags=["data-flow", "security", "validation", "transformations"],
            metadata={"specification": "024", "priority": "CRITICAL"},
        )
        self._exec_reader = ExecutionPlanReader()
        self._struct_reader = ProjectStructureReader()
        self._mod_reader = ModuleArchitectureReader()
        self._comp_reader = ComponentArchitectureReader()
        self._iface_reader = InterfaceContractReader()
        self._req_reader = RequirementNormalizationReader()
        self._mapper = FlowMapper()
        self._validator = FlowValidator()
        self._cache = CacheManager(enabled=True)
        self._quality_gate = QualityGate()
        self._builder = BlueprintBuilder()

    def execute(self, context: GenerationContext) -> StageResult:
        try:
            _log.info("DataFlowPlanningEngine starting (Spec 024)")

            exec_data = self._exec_reader.read(context)
            struct_data = self._struct_reader.read(context)
            mod_data = self._mod_reader.read(context)
            comp_data = self._comp_reader.read(context)
            iface_data = self._iface_reader.read(context)
            req_data = self._req_reader.read(context)

            sources_used, sources_missing = [], []
            for name, data in [
                (SOURCE_EXECUTION_PLAN, exec_data),
                (SOURCE_PROJECT_STRUCTURE, struct_data),
                (SOURCE_MODULE_ARCHITECTURE, mod_data),
                (SOURCE_COMPONENT_ARCHITECTURE, comp_data),
                (SOURCE_INTERFACE_CONTRACT, iface_data),
                (SOURCE_NORMALIZED_REQUIREMENTS, req_data),
            ]:
                (sources_used if data.available else sources_missing).append(name)

            cache_key = self._cache.make_key(
                exec_data.raw, struct_data.raw, mod_data.raw,
                comp_data.raw, iface_data.raw, req_data.raw,
            )
            cached = self._cache.get(cache_key)
            if cached is not None:
                bp = DataFlowBlueprint(**{
                    k: v for k, v in cached.items()
                    if k in DataFlowBlueprint.__dataclass_fields__
                })
                bp.cache_info = self._cache.info_for_hit(cache_key)
                context.set("data_flow_blueprint", bp)
                return self.ok(
                    outputs={"data_flow_blueprint": bp.to_dict()},
                    metadata={"cache": "hit"},
                )

            sources, destinations, paths, validations, security, errors = self._mapper.map(
                exec_data, struct_data, mod_data, comp_data, iface_data, req_data,
            )
            conflicts = self._validator.validate(sources, destinations, paths)

            confidence = self._confidence(sources_used, sources_missing, conflicts, paths)

            bp = self._builder.build(
                sources=sources,
                destinations=destinations,
                paths=paths,
                validation_rules=validations,
                security_rules=security,
                error_flows=errors,
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
            context.set("data_flow_blueprint", bp)

            _log.info(
                "DataFlowPlanningEngine finished — verdict=%s paths=%d sources=%d",
                verdict, len(paths), len(sources),
            )

            if not passed:
                return self.failed(
                    errors=[f"Data Flow failed quality gate (verdict={verdict})"],
                    outputs={"data_flow_blueprint": bp_dict},
                    warnings=[f.message for f in gate_findings],
                )
            return self.ok(
                outputs={"data_flow_blueprint": bp_dict},
                metadata={
                    "blueprint_id": bp.blueprint_id,
                    "verdict": verdict,
                    "path_count": len(paths),
                    "source_count": len(sources),
                    "conflict_count": len(conflicts),
                    "confidence": confidence,
                },
            )
        except Exception as exc:
            _log.exception("DataFlowPlanningEngine crashed: %s", exc)
            return self.failed(errors=[f"DataFlowPlanningEngine error: {exc}"])

    def _confidence(self, used, missing, conflicts, paths) -> float:
        total = len(ALL_SOURCES)
        ratio = len(used) / total if total else 0.0
        crit = sum(1 for c in conflicts if getattr(c, "severity", "") == "critical")
        penalty = min(0.4, crit * 0.15)
        richness = min(1.0, len(paths) / 5.0)
        conf = (0.5 * ratio) + (0.3 * richness) + 0.2 - penalty
        return round(max(0.0, min(1.0, conf)), 3)


__all__ = ["DataFlowPlanningEngine"]
