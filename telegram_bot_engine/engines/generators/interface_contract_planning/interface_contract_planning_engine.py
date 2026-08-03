"""
InterfaceContractPlanningEngine — Specification 023

Designs all interfaces and contracts that govern communication
between modules and components. Produces the Interface & Contract Blueprint.
"""

from __future__ import annotations

import logging
from typing import List

from ....core.context import GenerationContext
from ....core.result import StageResult
from ...base.base_engine import BaseEngine
from .data_readers import (
    ExecutionPlanReader,
    ProjectStructureReader,
    ModuleArchitectureReader,
    ComponentArchitectureReader,
    ArchitectureDecisionReader,
)
from .report_data import (
    InterfaceContractBlueprint,
    ALL_SOURCES,
    SOURCE_EXECUTION_PLAN,
    SOURCE_PROJECT_STRUCTURE,
    SOURCE_MODULE_ARCHITECTURE,
    SOURCE_COMPONENT_ARCHITECTURE,
    SOURCE_ARCHITECTURE_DECISION,
)
from .interface_discoverer import InterfaceDiscoverer
from .architecture_validator import ArchitectureValidator
from .cache_manager import CacheManager
from .quality_gate import QualityGate
from .blueprint_builder import BlueprintBuilder

_log = logging.getLogger("engine.interface_contract_planning")


class InterfaceContractPlanningEngine(BaseEngine):
    """Specification 023 — Interface & Contract Planning Engine."""

    def __init__(self) -> None:
        super().__init__(
            name="interface_contract_planning",
            version="1.0.0",
            description=(
                "Designs all interfaces and contracts that regulate "
                "communication between modules and components."
            ),
            tags=["interfaces", "contracts", "communication", "isolation"],
            metadata={"specification": "023", "priority": "CRITICAL"},
        )
        self._exec_reader = ExecutionPlanReader()
        self._struct_reader = ProjectStructureReader()
        self._mod_reader = ModuleArchitectureReader()
        self._comp_reader = ComponentArchitectureReader()
        self._arch_reader = ArchitectureDecisionReader()
        self._discoverer = InterfaceDiscoverer()
        self._validator = ArchitectureValidator()
        self._cache = CacheManager(enabled=True)
        self._quality_gate = QualityGate()
        self._builder = BlueprintBuilder()

    def execute(self, context: GenerationContext) -> StageResult:
        try:
            _log.info("InterfaceContractPlanningEngine starting (Spec 023)")

            exec_data = self._exec_reader.read(context)
            struct_data = self._struct_reader.read(context)
            mod_data = self._mod_reader.read(context)
            comp_data = self._comp_reader.read(context)
            arch_data = self._arch_reader.read(context)

            sources_used, sources_missing = [], []
            for name, data in [
                (SOURCE_EXECUTION_PLAN, exec_data),
                (SOURCE_PROJECT_STRUCTURE, struct_data),
                (SOURCE_MODULE_ARCHITECTURE, mod_data),
                (SOURCE_COMPONENT_ARCHITECTURE, comp_data),
                (SOURCE_ARCHITECTURE_DECISION, arch_data),
            ]:
                (sources_used if data.available else sources_missing).append(name)

            cache_key = self._cache.make_key(
                exec_data.raw, struct_data.raw, mod_data.raw, comp_data.raw, arch_data.raw,
            )
            cached = self._cache.get(cache_key)
            if cached is not None:
                bp = InterfaceContractBlueprint(**{
                    k: v for k, v in cached.items()
                    if k in InterfaceContractBlueprint.__dataclass_fields__
                })
                bp.cache_info = self._cache.info_for_hit(cache_key)
                context.set("interface_contract_blueprint", bp)
                return self.ok(
                    outputs={"interface_contract_blueprint": bp.to_dict()},
                    metadata={"cache": "hit"},
                )

            interfaces, contracts, comm_rules, dep_rules = self._discoverer.discover(
                comp_data, mod_data, arch_data,
            )
            conflicts = self._validator.validate(interfaces, contracts)

            confidence = self._confidence(sources_used, sources_missing, conflicts, interfaces)

            bp = self._builder.build(
                interfaces=interfaces,
                contracts=contracts,
                communication_rules=comm_rules,
                dependency_rules=dep_rules,
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
            context.set("interface_contract_blueprint", bp)

            _log.info(
                "InterfaceContractPlanningEngine finished — verdict=%s interfaces=%d contracts=%d",
                verdict, len(interfaces), len(contracts),
            )

            if not passed:
                return self.failed(
                    errors=[f"Interface & Contract failed quality gate (verdict={verdict})"],
                    outputs={"interface_contract_blueprint": bp_dict},
                    warnings=[f.message for f in gate_findings],
                )
            return self.ok(
                outputs={"interface_contract_blueprint": bp_dict},
                metadata={
                    "blueprint_id": bp.blueprint_id,
                    "verdict": verdict,
                    "interface_count": len(interfaces),
                    "contract_count": len(contracts),
                    "conflict_count": len(conflicts),
                    "confidence": confidence,
                },
            )
        except Exception as exc:
            _log.exception("InterfaceContractPlanningEngine crashed: %s", exc)
            return self.failed(errors=[f"InterfaceContractPlanningEngine error: {exc}"])

    def _confidence(self, used, missing, conflicts, interfaces) -> float:
        total = len(ALL_SOURCES)
        ratio = len(used) / total if total else 0.0
        crit = sum(1 for c in conflicts if getattr(c, "severity", "") == "critical")
        penalty = min(0.4, crit * 0.15)
        richness = min(1.0, len(interfaces) / 10.0)
        conf = (0.5 * ratio) + (0.3 * richness) + 0.2 - penalty
        return round(max(0.0, min(1.0, conf)), 3)


__all__ = ["InterfaceContractPlanningEngine"]
