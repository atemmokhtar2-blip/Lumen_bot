"""
ComponentArchitecturePlanningEngine — Specification 022

Splits every module into independent components with clear responsibilities.
Produces the Component Architecture Blueprint.
"""

from __future__ import annotations

import logging
from typing import List

from ....core.context import GenerationContext
from ....core.result import StageResult
from ...base.base_engine import BaseEngine
from .data_readers import (
    ModuleArchitectureReader,
    ProjectStructureReader,
    ExecutionPlanReader,
    ArchitectureDecisionReader,
    RequirementNormalizationReader,
)
from .report_data import (
    ComponentArchitectureBlueprint,
    ALL_SOURCES,
    SOURCE_MODULE_ARCHITECTURE,
    SOURCE_PROJECT_STRUCTURE,
    SOURCE_EXECUTION_PLAN,
    SOURCE_ARCHITECTURE_DECISION,
    SOURCE_NORMALIZED_REQUIREMENTS,
)
from .component_discoverer import ComponentDiscoverer
from .dependency_analyzer import DependencyAnalyzer
from .architecture_validator import ArchitectureValidator
from .cache_manager import CacheManager
from .quality_gate import QualityGate
from .blueprint_builder import BlueprintBuilder

_log = logging.getLogger("engine.component_architecture_planning")


class ComponentArchitecturePlanningEngine(BaseEngine):
    """Specification 022 — Component Architecture Planning Engine."""

    def __init__(self) -> None:
        super().__init__(
            name="component_architecture_planning",
            version="1.0.0",
            description=(
                "Splits every module into independent components with clear "
                "responsibilities, interfaces and dependencies."
            ),
            tags=["components", "architecture", "interfaces"],
            metadata={"specification": "022", "priority": "CRITICAL"},
        )
        self._mod_reader = ModuleArchitectureReader()
        self._struct_reader = ProjectStructureReader()
        self._exec_reader = ExecutionPlanReader()
        self._arch_reader = ArchitectureDecisionReader()
        self._req_reader = RequirementNormalizationReader()
        self._discoverer = ComponentDiscoverer()
        self._dep_analyzer = DependencyAnalyzer()
        self._validator = ArchitectureValidator()
        self._cache = CacheManager(enabled=True)
        self._quality_gate = QualityGate()
        self._builder = BlueprintBuilder()

    def execute(self, context: GenerationContext) -> StageResult:
        try:
            _log.info("ComponentArchitecturePlanningEngine starting (Spec 022)")

            mod_data = self._mod_reader.read(context)
            struct_data = self._struct_reader.read(context)
            exec_data = self._exec_reader.read(context)
            arch_data = self._arch_reader.read(context)
            req_data = self._req_reader.read(context)

            sources_used, sources_missing = [], []
            for name, data in [
                (SOURCE_MODULE_ARCHITECTURE, mod_data),
                (SOURCE_PROJECT_STRUCTURE, struct_data),
                (SOURCE_EXECUTION_PLAN, exec_data),
                (SOURCE_ARCHITECTURE_DECISION, arch_data),
                (SOURCE_NORMALIZED_REQUIREMENTS, req_data),
            ]:
                (sources_used if data.available else sources_missing).append(name)

            cache_key = self._cache.make_key(
                mod_data.raw, struct_data.raw, exec_data.raw, arch_data.raw, req_data.raw,
            )
            cached = self._cache.get(cache_key)
            if cached is not None:
                bp = ComponentArchitectureBlueprint(**{
                    k: v for k, v in cached.items()
                    if k in ComponentArchitectureBlueprint.__dataclass_fields__
                })
                bp.cache_info = self._cache.info_for_hit(cache_key)
                context.set("component_architecture_blueprint", bp)
                return self.ok(
                    outputs={"component_architecture_blueprint": bp.to_dict()},
                    metadata={"cache": "hit"},
                )

            components = self._discoverer.discover(mod_data, arch_data)
            relations, dep_conflicts, dep_graph, reuses = self._dep_analyzer.analyze(components)
            val_conflicts = self._validator.validate(components)
            all_conflicts = dep_conflicts + val_conflicts

            confidence = self._confidence(sources_used, sources_missing, all_conflicts, components)

            bp = self._builder.build(
                components=components,
                relations=relations,
                conflicts=all_conflicts,
                reuses=reuses,
                dependency_graph=dep_graph,
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
            context.set("component_architecture_blueprint", bp)

            _log.info(
                "ComponentArchitecturePlanningEngine finished — verdict=%s components=%d",
                verdict, len(components),
            )

            if not passed:
                return self.failed(
                    errors=[f"Component Architecture failed quality gate (verdict={verdict})"],
                    outputs={"component_architecture_blueprint": bp_dict},
                    warnings=[f.message for f in gate_findings],
                )
            return self.ok(
                outputs={"component_architecture_blueprint": bp_dict},
                metadata={
                    "blueprint_id": bp.blueprint_id,
                    "verdict": verdict,
                    "component_count": len(components),
                    "conflict_count": len(all_conflicts),
                    "reuse_count": len(reuses),
                    "confidence": confidence,
                },
            )
        except Exception as exc:
            _log.exception("ComponentArchitecturePlanningEngine crashed: %s", exc)
            return self.failed(errors=[f"ComponentArchitecturePlanningEngine error: {exc}"])

    def _confidence(self, used, missing, conflicts, components) -> float:
        total = len(ALL_SOURCES)
        ratio = len(used) / total if total else 0.0
        crit = sum(1 for c in conflicts if getattr(c, "severity", "") == "critical")
        penalty = min(0.4, crit * 0.15)
        richness = min(1.0, len(components) / 15.0)
        conf = (0.5 * ratio) + (0.3 * richness) + 0.2 - penalty
        return round(max(0.0, min(1.0, conf)), 3)


__all__ = ["ComponentArchitecturePlanningEngine"]
