"""
ExecutionPlanningEngine — Specification 019

Main engine class that orchestrates the creation of a complete
Execution Plan.

This engine:

1. Reads all required data sources (Normalized Requirement Model,
   Architecture Decision Report, Technology Selection Report,
   Risk Analysis Report, Project Capability Report, Knowledge Base).
2. Partitions the work into ordered execution phases.
3. Seeds each phase with concrete tasks derived from upstream artefacts.
4. Builds the full dependency graph and detects circular / missing deps.
5. Detects tasks that can safely run in parallel.
6. Detects residual ordering and structural conflicts.
7. Assembles the final Execution Plan.
8. Validates the plan through the Quality Gate (blocks the pipeline
   if the plan is not 100 % valid).

The engine does NOT write code, create files, or start the build
process.  Its sole function is to produce the *Execution Plan* —
the official, ordered blueprint that every subsequent engine must
follow.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List

from ....core.context import GenerationContext
from ....core.result import StageResult
from ...base.base_engine import BaseEngine
from .data_readers import (
    RequirementNormalizationData,
    ArchitectureDecisionData,
    TechnologySelectionData,
    RiskAnalysisData,
    ProjectCapabilityData,
    KnowledgeData,
    RequirementNormalizationReader,
    ArchitectureDecisionReader,
    TechnologySelectionReader,
    RiskAnalysisReader,
    ProjectCapabilityReader,
    KnowledgeReader,
)
from .report_data import (
    ExecutionPlan,
    ALL_SOURCES,
    SOURCE_NORMALIZED_REQUIREMENTS,
    SOURCE_ARCHITECTURE_DECISION,
    SOURCE_TECHNOLOGY_SELECTION,
    SOURCE_RISK_ANALYSIS,
    SOURCE_PROJECT_CAPABILITY,
    SOURCE_KNOWLEDGE_BASE,
    CONFIDENCE_HIGH_THRESHOLD,
    CONFIDENCE_MEDIUM_THRESHOLD,
)
from .phase_planner import PhasePlanner
from .dependency_analyzer import DependencyAnalyzer
from .parallel_detector import ParallelDetector
from .conflict_detector import ConflictDetector
from .cache_manager import CacheManager
from .quality_gate import QualityGate
from .plan_builder import PlanBuilder

_log = logging.getLogger("engine.execution_planning")


class ExecutionPlanningEngine(BaseEngine):
    """Specification 019 — Execution Planning Engine."""

    def __init__(self) -> None:
        super().__init__(
            name="execution_planning",
            version="1.0.0",
            description=(
                "Converts all previous analysis and planning artefacts "
                "into a precise, ordered Execution Plan that the rest "
                "of the system can follow step by step."
            ),
            tags=["planning", "execution", "ordering", "phases"],
            metadata={"specification": "019", "priority": "CRITICAL"},
        )
        self._req_reader = RequirementNormalizationReader()
        self._arch_reader = ArchitectureDecisionReader()
        self._tech_reader = TechnologySelectionReader()
        self._risk_reader = RiskAnalysisReader()
        self._cap_reader = ProjectCapabilityReader()
        self._kb_reader = KnowledgeReader()

        self._phase_planner = PhasePlanner()
        self._dependency_analyzer = DependencyAnalyzer()
        self._parallel_detector = ParallelDetector()
        self._conflict_detector = ConflictDetector()
        self._cache_manager = CacheManager(enabled=True)
        self._quality_gate = QualityGate()
        self._plan_builder = PlanBuilder()

    def execute(self, context: GenerationContext) -> StageResult:
        """Run the full Execution Planning pipeline."""
        try:
            _log.info("ExecutionPlanningEngine starting (Spec 019)")

            # ---------------------------------------------------------- #
            # 1. Read all data sources (tolerant)
            # ---------------------------------------------------------- #
            req_data = self._req_reader.read(context)
            arch_data = self._arch_reader.read(context)
            tech_data = self._tech_reader.read(context)
            risk_data = self._risk_reader.read(context)
            cap_data = self._cap_reader.read(context)
            kb_data = self._kb_reader.read(context)

            sources_used: List[str] = []
            sources_missing: List[str] = []
            source_map = [
                (SOURCE_NORMALIZED_REQUIREMENTS, req_data),
                (SOURCE_ARCHITECTURE_DECISION, arch_data),
                (SOURCE_TECHNOLOGY_SELECTION, tech_data),
                (SOURCE_RISK_ANALYSIS, risk_data),
                (SOURCE_PROJECT_CAPABILITY, cap_data),
                (SOURCE_KNOWLEDGE_BASE, kb_data),
            ]
            for name, data in source_map:
                if data.available:
                    sources_used.append(name)
                else:
                    sources_missing.append(name)

            _log.info(
                "Sources available: %s | missing: %s",
                sources_used, sources_missing,
            )

            # ---------------------------------------------------------- #
            # 2. Cache lookup
            # ---------------------------------------------------------- #
            cache_key = self._cache_manager.make_key(
                req_data.raw, arch_data.raw, tech_data.raw,
                risk_data.raw, cap_data.raw, kb_data.raw,
            )
            cached = self._cache_manager.get(cache_key)
            if cached is not None:
                _log.info("Returning cached Execution Plan")
                plan = ExecutionPlan(**{
                    k: v for k, v in cached.items()
                    if k in ExecutionPlan.__dataclass_fields__
                })
                # Re-attach cache info
                plan.cache_info = self._cache_manager.info_for_hit(cache_key)
                context.set("execution_plan", plan)
                return self.ok(
                    outputs={"execution_plan": plan.to_dict()},
                    metadata={"cache": "hit", "plan_id": plan.plan_id},
                )

            # ---------------------------------------------------------- #
            # 3. Phase planning + task seeding
            # ---------------------------------------------------------- #
            phases = self._phase_planner.plan(
                req_data, arch_data, tech_data, risk_data, cap_data, kb_data,
            )

            # ---------------------------------------------------------- #
            # 4. Dependency analysis
            # ---------------------------------------------------------- #
            dependencies, dep_conflicts = self._dependency_analyzer.analyze(phases)

            # ---------------------------------------------------------- #
            # 5. Parallel detection
            # ---------------------------------------------------------- #
            parallel_groups, sequential_ids = self._parallel_detector.detect(
                phases, dependencies,
            )

            # ---------------------------------------------------------- #
            # 6. Residual conflict detection
            # ---------------------------------------------------------- #
            extra_conflicts = self._conflict_detector.detect(
                phases, dependencies, parallel_groups,
            )
            all_conflicts = dep_conflicts + extra_conflicts

            # ---------------------------------------------------------- #
            # 7. Confidence score
            # ---------------------------------------------------------- #
            confidence = self._compute_confidence(
                sources_used, sources_missing, all_conflicts, phases,
            )

            # ---------------------------------------------------------- #
            # 8. Assemble the plan
            # ---------------------------------------------------------- #
            plan = self._plan_builder.build(
                phases=phases,
                dependencies=dependencies,
                parallel_groups=parallel_groups,
                sequential_task_ids=sequential_ids,
                conflicts=all_conflicts,
                findings=[],  # QualityGate will add its own
                sources_used=sources_used,
                sources_missing=sources_missing,
                confidence=confidence,
            )

            # ---------------------------------------------------------- #
            # 9. Quality Gate
            # ---------------------------------------------------------- #
            gate_findings, passed, verdict = self._quality_gate.validate(plan)
            plan.findings.extend(gate_findings)
            plan.verdict = verdict
            plan.readiness_status = verdict

            # ---------------------------------------------------------- #
            # 10. Cache store + context write
            # ---------------------------------------------------------- #
            plan_dict = plan.to_dict()
            plan.cache_info = self._cache_manager.put(cache_key, plan_dict)

            context.set("execution_plan", plan)

            _log.info(
                "ExecutionPlanningEngine finished — verdict=%s "
                "phases=%d tasks=%d conflicts=%d confidence=%.2f",
                verdict,
                len(plan.phases),
                len(plan.tasks),
                len(plan.conflicts),
                confidence,
            )

            if not passed:
                return self.failed(
                    errors=[
                        f"Execution Plan failed quality gate (verdict={verdict})"
                    ],
                    outputs={"execution_plan": plan_dict},
                    warnings=[f.message for f in gate_findings],
                )

            return self.ok(
                outputs={"execution_plan": plan_dict},
                metadata={
                    "plan_id": plan.plan_id,
                    "verdict": verdict,
                    "phase_count": len(plan.phases),
                    "task_count": len(plan.tasks),
                    "conflict_count": len(plan.conflicts),
                    "confidence": confidence,
                },
            )

        except Exception as exc:
            _log.exception("ExecutionPlanningEngine crashed: %s", exc)
            return self.failed(errors=[f"ExecutionPlanningEngine error: {exc}"])

    def _compute_confidence(
        self,
        sources_used: List[str],
        sources_missing: List[str],
        conflicts: List[Any],
        phases: List[Any],
    ) -> float:
        """Simple heuristic confidence score between 0.0 and 1.0."""
        total_sources = len(ALL_SOURCES)
        source_ratio = len(sources_used) / total_sources if total_sources else 0.0

        critical_conflicts = sum(
            1 for c in conflicts if getattr(c, "severity", "") == "critical"
        )
        conflict_penalty = min(0.4, critical_conflicts * 0.15)

        task_count = sum(len(p.tasks) for p in phases)
        richness = min(1.0, task_count / 15.0)  # expect ~15+ tasks for full plan

        confidence = (0.5 * source_ratio) + (0.3 * richness) + 0.2
        confidence = max(0.0, min(1.0, confidence - conflict_penalty))
        return round(confidence, 3)


__all__ = ["ExecutionPlanningEngine"]
