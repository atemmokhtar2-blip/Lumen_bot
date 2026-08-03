"""
ResourceDependencyPlanningEngine — Specification 025

Plans all external dependencies and runtime resources before generation.
Produces the Resource & Dependency Blueprint.
"""

from __future__ import annotations

import logging

from ....core.context import GenerationContext
from ....core.result import StageResult
from ...base.base_engine import BaseEngine
from .data_readers import (
    ExecutionPlanReader, ProjectStructureReader, ModuleArchitectureReader,
    ComponentArchitectureReader, InterfaceContractReader, DataFlowReader,
    TechnologySelectionReader,
)
from .report_data import (
    ResourceDependencyBlueprint, ALL_SOURCES,
    SOURCE_EXECUTION_PLAN, SOURCE_PROJECT_STRUCTURE, SOURCE_MODULE_ARCHITECTURE,
    SOURCE_COMPONENT_ARCHITECTURE, SOURCE_INTERFACE_CONTRACT, SOURCE_DATA_FLOW,
    SOURCE_TECHNOLOGY_SELECTION,
)
from .dependency_discoverer import DependencyDiscoverer
from .dependency_validator import DependencyValidator
from .cache_manager import CacheManager
from .quality_gate import QualityGate
from .blueprint_builder import BlueprintBuilder

_log = logging.getLogger("engine.resource_dependency_planning")


class ResourceDependencyPlanningEngine(BaseEngine):
    """Specification 025 — Resource & Dependency Planning Engine."""

    def __init__(self) -> None:
        super().__init__(
            name="resource_dependency_planning",
            version="1.0.0",
            description=(
                "Plans all libraries, frameworks, resources, versions, "
                "compatibility and risks before any file is generated."
            ),
            tags=["dependencies", "resources", "versions", "risks"],
            metadata={"specification": "025", "priority": "CRITICAL"},
        )
        self._exec_reader = ExecutionPlanReader()
        self._struct_reader = ProjectStructureReader()
        self._mod_reader = ModuleArchitectureReader()
        self._comp_reader = ComponentArchitectureReader()
        self._iface_reader = InterfaceContractReader()
        self._flow_reader = DataFlowReader()
        self._tech_reader = TechnologySelectionReader()
        self._discoverer = DependencyDiscoverer()
        self._validator = DependencyValidator()
        self._cache = CacheManager(enabled=True)
        self._quality_gate = QualityGate()
        self._builder = BlueprintBuilder()

    def execute(self, context: GenerationContext) -> StageResult:
        try:
            _log.info("ResourceDependencyPlanningEngine starting (Spec 025)")

            exec_data = self._exec_reader.read(context)
            struct_data = self._struct_reader.read(context)
            mod_data = self._mod_reader.read(context)
            comp_data = self._comp_reader.read(context)
            iface_data = self._iface_reader.read(context)
            flow_data = self._flow_reader.read(context)
            tech_data = self._tech_reader.read(context)

            sources_used, sources_missing = [], []
            for name, data in [
                (SOURCE_EXECUTION_PLAN, exec_data),
                (SOURCE_PROJECT_STRUCTURE, struct_data),
                (SOURCE_MODULE_ARCHITECTURE, mod_data),
                (SOURCE_COMPONENT_ARCHITECTURE, comp_data),
                (SOURCE_INTERFACE_CONTRACT, iface_data),
                (SOURCE_DATA_FLOW, flow_data),
                (SOURCE_TECHNOLOGY_SELECTION, tech_data),
            ]:
                (sources_used if data.available else sources_missing).append(name)

            cache_key = self._cache.make_key(
                exec_data.raw, struct_data.raw, mod_data.raw, comp_data.raw,
                iface_data.raw, flow_data.raw, tech_data.raw,
            )
            cached = self._cache.get(cache_key)
            if cached is not None:
                bp = ResourceDependencyBlueprint(**{
                    k: v for k, v in cached.items()
                    if k in ResourceDependencyBlueprint.__dataclass_fields__
                })
                bp.cache_info = self._cache.info_for_hit(cache_key)
                context.set("resource_dependency_blueprint", bp)
                return self.ok(
                    outputs={"resource_dependency_blueprint": bp.to_dict()},
                    metadata={"cache": "hit"},
                )

            deps, resources, matrix, risks, opts, py_ver = self._discoverer.discover(
                tech_data, comp_data, flow_data, struct_data,
            )
            conflicts = self._validator.validate(deps, resources)

            confidence = self._confidence(sources_used, sources_missing, conflicts, deps)

            bp = self._builder.build(
                dependencies=deps,
                resources=resources,
                version_matrix=matrix,
                risks=risks,
                optimizations=opts,
                conflicts=conflicts,
                python_version=py_ver,
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
            context.set("resource_dependency_blueprint", bp)

            _log.info(
                "ResourceDependencyPlanningEngine finished — verdict=%s deps=%d resources=%d",
                verdict, len(deps), len(resources),
            )

            if not passed:
                return self.failed(
                    errors=[f"Resource & Dependency failed quality gate (verdict={verdict})"],
                    outputs={"resource_dependency_blueprint": bp_dict},
                    warnings=[f.message for f in gate_findings],
                )
            return self.ok(
                outputs={"resource_dependency_blueprint": bp_dict},
                metadata={
                    "blueprint_id": bp.blueprint_id,
                    "verdict": verdict,
                    "dep_count": len(deps),
                    "resource_count": len(resources),
                    "risk_count": len(risks),
                    "confidence": confidence,
                },
            )
        except Exception as exc:
            _log.exception("ResourceDependencyPlanningEngine crashed: %s", exc)
            return self.failed(errors=[f"ResourceDependencyPlanningEngine error: {exc}"])

    def _confidence(self, used, missing, conflicts, deps) -> float:
        total = len(ALL_SOURCES)
        ratio = len(used) / total if total else 0.0
        crit = sum(1 for c in conflicts if getattr(c, "severity", "") == "critical")
        penalty = min(0.4, crit * 0.15)
        richness = min(1.0, len(deps) / 8.0)
        conf = (0.5 * ratio) + (0.3 * richness) + 0.2 - penalty
        return round(max(0.0, min(1.0, conf)), 3)


__all__ = ["ResourceDependencyPlanningEngine"]
