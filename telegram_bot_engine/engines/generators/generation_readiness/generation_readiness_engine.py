"""
GenerationReadinessEngine — Specification 027

Final validation gate before any code or file generation.
Produces the Generation Readiness Report. Requires 100% readiness.
"""

from __future__ import annotations

import logging

from ....core.context import GenerationContext
from ....core.result import StageResult
from ...base.base_engine import BaseEngine
from .data_readers import (
    ExecutionPlanReader, ProjectStructureReader, ModuleArchitectureReader,
    ComponentArchitectureReader, InterfaceContractReader, DataFlowReader,
    ResourceDependencyReader, GenerationStrategyReader,
)
from .report_data import (
    GenerationReadinessReport, ALL_SOURCES,
    SOURCE_EXECUTION_PLAN, SOURCE_PROJECT_STRUCTURE, SOURCE_MODULE_ARCHITECTURE,
    SOURCE_COMPONENT_ARCHITECTURE, SOURCE_INTERFACE_CONTRACT, SOURCE_DATA_FLOW,
    SOURCE_RESOURCE_DEPENDENCY, SOURCE_GENERATION_STRATEGY,
    REQUIRED_READINESS,
)
from .readiness_checker import ReadinessChecker
from .cache_manager import CacheManager
from .quality_gate import QualityGate
from .blueprint_builder import BlueprintBuilder

_log = logging.getLogger("engine.generation_readiness")


class GenerationReadinessEngine(BaseEngine):
    """Specification 027 — Generation Readiness Validation Engine."""

    def __init__(self) -> None:
        super().__init__(
            name="generation_readiness",
            version="1.0.0",
            description=(
                "Final validation gate before generation. Verifies all upstream "
                "blueprints are complete, consistent and free of critical issues. "
                "Requires 100% readiness to approve generation."
            ),
            tags=["readiness", "validation", "gate", "final"],
            metadata={"specification": "027", "priority": "CRITICAL"},
        )
        self._exec_reader = ExecutionPlanReader()
        self._struct_reader = ProjectStructureReader()
        self._mod_reader = ModuleArchitectureReader()
        self._comp_reader = ComponentArchitectureReader()
        self._iface_reader = InterfaceContractReader()
        self._flow_reader = DataFlowReader()
        self._res_reader = ResourceDependencyReader()
        self._strat_reader = GenerationStrategyReader()
        self._checker = ReadinessChecker()
        self._cache = CacheManager(enabled=True)
        self._quality_gate = QualityGate()
        self._builder = BlueprintBuilder()

    def execute(self, context: GenerationContext) -> StageResult:
        try:
            _log.info("GenerationReadinessEngine starting (Spec 027)")

            snapshots = {
                SOURCE_EXECUTION_PLAN: self._exec_reader.read(context),
                SOURCE_PROJECT_STRUCTURE: self._struct_reader.read(context),
                SOURCE_MODULE_ARCHITECTURE: self._mod_reader.read(context),
                SOURCE_COMPONENT_ARCHITECTURE: self._comp_reader.read(context),
                SOURCE_INTERFACE_CONTRACT: self._iface_reader.read(context),
                SOURCE_DATA_FLOW: self._flow_reader.read(context),
                SOURCE_RESOURCE_DEPENDENCY: self._res_reader.read(context),
                SOURCE_GENERATION_STRATEGY: self._strat_reader.read(context),
            }

            sources_used, sources_missing = [], []
            for name, snap in snapshots.items():
                (sources_used if snap.available else sources_missing).append(name)

            cache_key = self._cache.make_key(*[s.raw for s in snapshots.values()])
            cached = self._cache.get(cache_key)
            if cached is not None:
                report = GenerationReadinessReport(**{
                    k: v for k, v in cached.items()
                    if k in GenerationReadinessReport.__dataclass_fields__
                })
                report.cache_info = self._cache.info_for_hit(cache_key)
                context.set("generation_readiness_report", report)
                return self.ok(
                    outputs={"generation_readiness_report": report.to_dict()},
                    metadata={"cache": "hit"},
                )

            scores, overall, issues, missing = self._checker.check(snapshots)

            confidence = self._confidence(sources_used, sources_missing, issues)

            report = self._builder.build(
                category_scores=scores,
                overall_score=overall,
                issues=issues,
                missing_items=missing,
                sources_used=sources_used,
                sources_missing=sources_missing,
                confidence=confidence,
            )

            gate_findings, passed, verdict, approval = self._quality_gate.validate(report)
            report.findings.extend(gate_findings)
            report.verdict = verdict
            report.readiness_status = verdict
            report.approval_status = approval

            report_dict = report.to_dict()
            report.cache_info = self._cache.put(cache_key, report_dict)
            context.set("generation_readiness_report", report)

            _log.info(
                "GenerationReadinessEngine finished — score=%.1f verdict=%s approval=%s",
                overall, verdict, approval,
            )

            if not passed:
                return self.failed(
                    errors=[
                        f"Generation readiness {overall}% < required {REQUIRED_READINESS}% "
                        f"(verdict={verdict}, approval={approval})"
                    ],
                    outputs={"generation_readiness_report": report_dict},
                    warnings=[f.message for f in gate_findings],
                )
            return self.ok(
                outputs={"generation_readiness_report": report_dict},
                metadata={
                    "report_id": report.report_id,
                    "verdict": verdict,
                    "approval_status": approval,
                    "overall_score": overall,
                    "issue_count": len(issues),
                    "missing_count": len(missing),
                    "confidence": confidence,
                },
            )
        except Exception as exc:
            _log.exception("GenerationReadinessEngine crashed: %s", exc)
            return self.failed(errors=[f"GenerationReadinessEngine error: {exc}"])

    def _confidence(self, used, missing, issues) -> float:
        total = len(ALL_SOURCES)
        ratio = len(used) / total if total else 0.0
        crit = sum(1 for i in issues if getattr(i, "severity", "") == "critical")
        penalty = min(0.4, crit * 0.1)
        conf = (0.7 * ratio) + 0.3 - penalty
        return round(max(0.0, min(1.0, conf)), 3)


__all__ = ["GenerationReadinessEngine"]
