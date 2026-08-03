"""
ProjectBuilderEngine — Specification 030

Intelligent Project Builder Engine.
First engine that scaffolds the project (folders + empty files) according
to the intelligent plan — without writing business logic.
"""

from __future__ import annotations

import logging

from ....core.context import GenerationContext
from ....core.result import StageResult
from ...base.base_engine import BaseEngine
from .data_readers import (
    CodePlanReader, StructureReader, ModuleArchitectureReader,
    ComponentArchitectureReader, StrategyReader, SessionReader,
)
from .report_data import (
    InitializedProjectReport, ALL_SOURCES,
    SOURCE_CODE_PLAN, SOURCE_STRUCTURE, SOURCE_MODULE_ARCH,
    SOURCE_COMPONENT_ARCH, SOURCE_STRATEGY, SOURCE_SESSION,
)
from .scaffold_builder import ScaffoldBuilder
from .cache_manager import CacheManager
from .quality_gate import QualityGate
from .blueprint_builder import BlueprintBuilder

_log = logging.getLogger("engine.project_builder")


class ProjectBuilderEngine(BaseEngine):
    """Specification 030 — Intelligent Project Builder Engine."""

    def __init__(self) -> None:
        super().__init__(
            name="project_builder",
            version="1.0.0",
            description=(
                "Scaffolds the project: creates folders, empty files, manifest "
                "and registry according to the intelligent plan. Does not write "
                "business logic."
            ),
            tags=["scaffold", "folders", "files", "manifest", "registry"],
            metadata={"specification": "030", "priority": "CRITICAL"},
        )
        self._plan_reader = CodePlanReader()
        self._struct_reader = StructureReader()
        self._mod_reader = ModuleArchitectureReader()
        self._comp_reader = ComponentArchitectureReader()
        self._strategy_reader = StrategyReader()
        self._session_reader = SessionReader()
        self._scaffold = ScaffoldBuilder()
        self._cache = CacheManager(enabled=True)
        self._quality_gate = QualityGate()
        self._builder = BlueprintBuilder()

    def execute(self, context: GenerationContext) -> StageResult:
        try:
            _log.info("ProjectBuilderEngine starting (Spec 030)")

            plan_data = self._plan_reader.read(context)
            struct_data = self._struct_reader.read(context)
            mod_data = self._mod_reader.read(context)
            comp_data = self._comp_reader.read(context)
            strategy_data = self._strategy_reader.read(context)
            session_data = self._session_reader.read(context)

            sources_used, sources_missing = [], []
            for name, data in [
                (SOURCE_CODE_PLAN, plan_data),
                (SOURCE_STRUCTURE, struct_data),
                (SOURCE_MODULE_ARCH, mod_data),
                (SOURCE_COMPONENT_ARCH, comp_data),
                (SOURCE_STRATEGY, strategy_data),
                (SOURCE_SESSION, session_data),
            ]:
                (sources_used if data.available else sources_missing).append(name)

            cache_key = self._cache.make_key(
                plan_data.raw, struct_data.raw, mod_data.raw,
                comp_data.raw, strategy_data.raw, session_data.raw,
            )
            cached = self._cache.get(cache_key)
            if cached is not None:
                report = InitializedProjectReport(**{
                    k: v for k, v in cached.items()
                    if k in InitializedProjectReport.__dataclass_fields__
                })
                report.cache_info = self._cache.info_for_hit(cache_key)
                context.set("initialized_project_report", report)
                return self.ok(
                    outputs={"initialized_project_report": report.to_dict()},
                    metadata={"cache": "hit"},
                )

            identity, entries, manifest, registry, logs, conflicts = self._scaffold.build(
                plan_data, struct_data, mod_data, comp_data, strategy_data, session_data,
            )

            confidence = self._confidence(sources_used, sources_missing, conflicts, entries)

            report = self._builder.build(
                identity=identity,
                entries=entries,
                manifest=manifest,
                registry=registry,
                logs=logs,
                conflicts=conflicts,
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
            context.set("initialized_project_report", report)

            _log.info(
                "ProjectBuilderEngine finished — verdict=%s folders=%d files=%d",
                verdict, report.folder_count, report.file_count,
            )

            if not passed:
                return self.failed(
                    errors=[f"Project Builder failed quality gate (verdict={verdict})"],
                    outputs={"initialized_project_report": report_dict},
                    warnings=[f.message for f in gate_findings],
                )
            return self.ok(
                outputs={"initialized_project_report": report_dict},
                metadata={
                    "report_id": report.report_id,
                    "project_id": identity.project_id,
                    "verdict": verdict,
                    "folder_count": report.folder_count,
                    "file_count": report.file_count,
                    "conflict_count": len(conflicts),
                    "confidence": confidence,
                },
            )
        except Exception as exc:
            _log.exception("ProjectBuilderEngine crashed: %s", exc)
            return self.failed(errors=[f"ProjectBuilderEngine error: {exc}"])

    def _confidence(self, used, missing, conflicts, entries) -> float:
        total = len(ALL_SOURCES)
        ratio = len(used) / total if total else 0.0
        crit = sum(1 for c in conflicts if getattr(c, "severity", "") == "critical")
        penalty = min(0.4, crit * 0.15)
        richness = min(1.0, len(entries) / 15.0)
        conf = (0.5 * ratio) + (0.3 * richness) + 0.2 - penalty
        return round(max(0.0, min(1.0, conf)), 3)


__all__ = ["ProjectBuilderEngine"]
