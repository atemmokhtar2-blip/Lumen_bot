"""
GenerationOrchestratorEngine — Specification 028

First engine that actually starts the generation process.
Does not write code itself — creates the session, distributes tasks,
sets up checkpoints and monitoring for downstream generators.
"""

from __future__ import annotations

import logging

from ....core.context import GenerationContext
from ....core.result import StageResult
from ...base.base_engine import BaseEngine
from .data_readers import (
    ReadinessReader, StrategyReader, ExecutionPlanReader,
    ProjectStructureReader, ModuleArchitectureReader,
    ComponentArchitectureReader, InterfaceContractReader,
    ResourceDependencyReader,
)
from .report_data import (
    GenerationSessionReport, ALL_SOURCES,
    SOURCE_READINESS, SOURCE_STRATEGY, SOURCE_EXECUTION_PLAN,
    SOURCE_PROJECT_STRUCTURE, SOURCE_MODULE_ARCHITECTURE,
    SOURCE_COMPONENT_ARCHITECTURE, SOURCE_INTERFACE_CONTRACT,
    SOURCE_RESOURCE_DEPENDENCY,
)
from .session_manager import SessionManager
from .cache_manager import CacheManager
from .quality_gate import QualityGate
from .blueprint_builder import BlueprintBuilder

_log = logging.getLogger("engine.generation_orchestrator")


class GenerationOrchestratorEngine(BaseEngine):
    """Specification 028 — Project Generation Orchestrator Engine."""

    def __init__(self) -> None:
        super().__init__(
            name="generation_orchestrator",
            version="1.0.0",
            description=(
                "Creates the generation session, distributes tasks to downstream "
                "generators, defines checkpoints and tracks progress. Does not "
                "write code itself — it orchestrates the generation process."
            ),
            tags=["orchestrator", "session", "tasks", "checkpoints"],
            metadata={"specification": "028", "priority": "CRITICAL"},
        )
        self._readiness_reader = ReadinessReader()
        self._strategy_reader = StrategyReader()
        self._exec_reader = ExecutionPlanReader()
        self._struct_reader = ProjectStructureReader()
        self._mod_reader = ModuleArchitectureReader()
        self._comp_reader = ComponentArchitectureReader()
        self._iface_reader = InterfaceContractReader()
        self._res_reader = ResourceDependencyReader()
        self._session_mgr = SessionManager()
        self._cache = CacheManager(enabled=True)
        self._quality_gate = QualityGate()
        self._builder = BlueprintBuilder()

    def execute(self, context: GenerationContext) -> StageResult:
        try:
            _log.info("GenerationOrchestratorEngine starting (Spec 028)")

            readiness_data = self._readiness_reader.read(context)
            strategy_data = self._strategy_reader.read(context)
            exec_data = self._exec_reader.read(context)
            struct_data = self._struct_reader.read(context)
            mod_data = self._mod_reader.read(context)
            comp_data = self._comp_reader.read(context)
            iface_data = self._iface_reader.read(context)
            res_data = self._res_reader.read(context)

            sources_used, sources_missing = [], []
            for name, data in [
                (SOURCE_READINESS, readiness_data),
                (SOURCE_STRATEGY, strategy_data),
                (SOURCE_EXECUTION_PLAN, exec_data),
                (SOURCE_PROJECT_STRUCTURE, struct_data),
                (SOURCE_MODULE_ARCHITECTURE, mod_data),
                (SOURCE_COMPONENT_ARCHITECTURE, comp_data),
                (SOURCE_INTERFACE_CONTRACT, iface_data),
                (SOURCE_RESOURCE_DEPENDENCY, res_data),
            ]:
                (sources_used if data.available else sources_missing).append(name)

            cache_key = self._cache.make_key(
                readiness_data.raw, strategy_data.raw, exec_data.raw,
                struct_data.raw, mod_data.raw, comp_data.raw,
                iface_data.raw, res_data.raw,
            )
            cached = self._cache.get(cache_key)
            if cached is not None:
                report = GenerationSessionReport(**{
                    k: v for k, v in cached.items()
                    if k in GenerationSessionReport.__dataclass_fields__
                })
                report.cache_info = self._cache.info_for_hit(cache_key)
                context.set("generation_session_report", report)
                return self.ok(
                    outputs={"generation_session_report": report.to_dict()},
                    metadata={"cache": "hit"},
                )

            project_id = ""
            if struct_data.raw:
                project_id = str(struct_data.raw.get("project_name") or "")

            (
                session_id, project_id, tasks, checkpoints, logs,
                progress, readiness_approved, readiness_score,
            ) = self._session_mgr.create_session(
                strategy_data, readiness_data, project_id=project_id,
            )

            confidence = self._confidence(
                sources_used, sources_missing, readiness_approved, tasks,
            )

            report = self._builder.build(
                session_id=session_id,
                project_id=project_id,
                tasks=tasks,
                checkpoints=checkpoints,
                logs=logs,
                progress=progress,
                readiness_approved=readiness_approved,
                readiness_score=readiness_score,
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
            context.set("generation_session_report", report)

            _log.info(
                "GenerationOrchestratorEngine finished — session=%s verdict=%s tasks=%d",
                session_id[:8], verdict, len(tasks),
            )

            if not passed:
                return self.failed(
                    errors=[f"Orchestrator failed quality gate (verdict={verdict})"],
                    outputs={"generation_session_report": report_dict},
                    warnings=[f.message for f in gate_findings],
                )
            return self.ok(
                outputs={"generation_session_report": report_dict},
                metadata={
                    "session_id": session_id,
                    "project_id": project_id,
                    "verdict": verdict,
                    "task_count": len(tasks),
                    "checkpoint_count": len(checkpoints),
                    "readiness_approved": readiness_approved,
                    "readiness_score": readiness_score,
                    "confidence": confidence,
                },
            )
        except Exception as exc:
            _log.exception("GenerationOrchestratorEngine crashed: %s", exc)
            return self.failed(errors=[f"GenerationOrchestratorEngine error: {exc}"])

    def _confidence(self, used, missing, approved, tasks) -> float:
        total = len(ALL_SOURCES)
        ratio = len(used) / total if total else 0.0
        approval_bonus = 0.15 if approved else 0.0
        richness = min(1.0, len(tasks) / 10.0)
        conf = (0.5 * ratio) + (0.25 * richness) + 0.1 + approval_bonus
        return round(max(0.0, min(1.0, conf)), 3)


__all__ = ["GenerationOrchestratorEngine"]
