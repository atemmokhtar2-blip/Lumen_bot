"""
ModuleArchitecturePlanningEngine — Specification 021

Designs the complete logical module architecture before any file is created.
Produces the Module Architecture Blueprint.
"""

from __future__ import annotations

import logging
from typing import Any, List

from ....core.context import GenerationContext
from ....core.result import StageResult
from ...base.base_engine import BaseEngine
from .data_readers import (
    ExecutionPlanReader,
    ProjectStructureReader,
    ArchitectureDecisionReader,
    RequirementNormalizationReader,
    TechnologySelectionReader,
)
from .report_data import (
    ModuleArchitectureBlueprint,
    ALL_SOURCES,
    SOURCE_EXECUTION_PLAN,
    SOURCE_PROJECT_STRUCTURE,
    SOURCE_ARCHITECTURE_DECISION,
    SOURCE_NORMALIZED_REQUIREMENTS,
    SOURCE_TECHNOLOGY_SELECTION,
)
from .module_discoverer import ModuleDiscoverer
from .dependency_analyzer import DependencyAnalyzer
from .architecture_validator import ArchitectureValidator
from .cache_manager import CacheManager
from .quality_gate import QualityGate
from .blueprint_builder import BlueprintBuilder

_log = logging.getLogger("engine.module_architecture_planning")


class ModuleArchitecturePlanningEngine(BaseEngine):
    """Specification 021 — Module Architecture Planning Engine."""

    def __init__(self) -> None:
        super().__init__(
            name="module_architecture_planning",
            version="1.0.0",
            description=(
                "Designs all logical modules of the project, assigns clear "
                "responsibilities, defines interfaces and prevents overlapping."
            ),
            tags=["modules", "architecture", "interfaces", "responsibilities"],
            metadata={"specification": "021", "priority": "CRITICAL"},
        )
        self._exec_reader = ExecutionPlanReader()
        self._struct_reader = ProjectStructureReader()
        self._arch_reader = ArchitectureDecisionReader()
        self._req_reader = RequirementNormalizationReader()
        self._tech_reader = TechnologySelectionReader()
        self._discoverer = ModuleDiscoverer()
        self._dep_analyzer = DependencyAnalyzer()
        self._validator = ArchitectureValidator()
        self._cache = CacheManager(enabled=True)
        self._quality_gate = QualityGate()
        self._builder = BlueprintBuilder()

    def execute(self, context: GenerationContext) -> StageResult:
        try:
            _log.info("ModuleArchitecturePlanningEngine starting (Spec 021)")

            exec_data = self._exec_reader.read(context)
            struct_data = self._struct_reader.read(context)
            arch_data = self._arch_reader.read(context)
            req_data = self._req_reader.read(context)
            tech_data = self._tech_reader.read(context)

            sources_used, sources_missing = [], []
            for name, data in [
                (SOURCE_EXECUTION_PLAN, exec_data),
                (SOURCE_PROJECT_STRUCTURE, struct_data),
                (SOURCE_ARCHITECTURE_DECISION, arch_data),
                (SOURCE_NORMALIZED_REQUIREMENTS, req_data),
                (SOURCE_TECHNOLOGY_SELECTION, tech_data),
            ]:
                (sources_used if data.available else sources_missing).append(name)

            cache_key = self._cache.make_key(
                exec_data.raw, struct_data.raw, arch_data.raw, req_data.raw, tech_data.raw,
            )
            cached = self._cache.get(cache_key)
            if cached is not None:
                bp = ModuleArchitectureBlueprint(**{
                    k: v for k, v in cached.items()
                    if k in ModuleArchitectureBlueprint.__dataclass_fields__
                })
                bp.cache_info = self._cache.info_for_hit(cache_key)
                context.set("module_architecture_blueprint", bp)
                return self.ok(
                    outputs={"module_architecture_blueprint": bp.to_dict()},
                    metadata={"cache": "hit"},
                )

            modules = self._discoverer.discover(
                exec_data, struct_data, arch_data, req_data, tech_data,
            )
            relations, dep_conflicts, dep_graph = self._dep_analyzer.analyze(modules)
            val_conflicts = self._validator.validate(modules)
            all_conflicts = dep_conflicts + val_conflicts

            confidence = self._compute_confidence(
                sources_used, sources_missing, all_conflicts, modules,
            )

            bp = self._builder.build(
                modules=modules,
                relations=relations,
                conflicts=all_conflicts,
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
            context.set("module_architecture_blueprint", bp)

            _log.info(
                "ModuleArchitecturePlanningEngine finished — verdict=%s modules=%d conflicts=%d",
                verdict, len(modules), len(all_conflicts),
            )

            if not passed:
                return self.failed(
                    errors=[f"Module Architecture failed quality gate (verdict={verdict})"],
                    outputs={"module_architecture_blueprint": bp_dict},
                    warnings=[f.message for f in gate_findings],
                )
            return self.ok(
                outputs={"module_architecture_blueprint": bp_dict},
                metadata={
                    "blueprint_id": bp.blueprint_id,
                    "verdict": verdict,
                    "module_count": len(modules),
                    "conflict_count": len(all_conflicts),
                    "confidence": confidence,
                },
            )
        except Exception as exc:
            _log.exception("ModuleArchitecturePlanningEngine crashed: %s", exc)
            return self.failed(errors=[f"ModuleArchitecturePlanningEngine error: {exc}"])

    def _compute_confidence(self, used, missing, conflicts, modules) -> float:
        total = len(ALL_SOURCES)
        ratio = len(used) / total if total else 0.0
        crit = sum(1 for c in conflicts if getattr(c, "severity", "") == "critical")
        penalty = min(0.4, crit * 0.15)
        richness = min(1.0, len(modules) / 10.0)
        conf = (0.5 * ratio) + (0.3 * richness) + 0.2 - penalty
        return round(max(0.0, min(1.0, conf)), 3)


__all__ = ["ModuleArchitecturePlanningEngine"]
