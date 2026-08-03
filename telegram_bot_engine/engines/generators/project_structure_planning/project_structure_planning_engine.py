"""
ProjectStructurePlanningEngine — Specification 020

Designs the complete project folder and file structure before any
file is created on disk.  Produces the Project Structure Blueprint.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List

from ....core.context import GenerationContext
from ....core.result import StageResult
from ...base.base_engine import BaseEngine
from .data_readers import (
    ExecutionPlanReader,
    ArchitectureDecisionReader,
    TechnologySelectionReader,
    RequirementNormalizationReader,
    ProjectCapabilityReader,
)
from .report_data import (
    ProjectStructureBlueprint,
    FileDependency,
    ALL_SOURCES,
    SOURCE_EXECUTION_PLAN,
    SOURCE_ARCHITECTURE_DECISION,
    SOURCE_TECHNOLOGY_SELECTION,
    SOURCE_NORMALIZED_REQUIREMENTS,
    SOURCE_PROJECT_CAPABILITY,
)
from .folder_planner import FolderPlanner
from .file_planner import FilePlanner
from .structure_validator import StructureValidator
from .cache_manager import CacheManager
from .quality_gate import QualityGate
from .blueprint_builder import BlueprintBuilder

_log = logging.getLogger("engine.project_structure_planning")


class ProjectStructurePlanningEngine(BaseEngine):
    """Specification 020 — Project Structure Planning Engine."""

    def __init__(self) -> None:
        super().__init__(
            name="project_structure_planning",
            version="1.0.0",
            description=(
                "Designs the complete project folder and file structure "
                "before any file is created. Produces the Project Structure Blueprint."
            ),
            tags=["structure", "folders", "files", "blueprint"],
            metadata={"specification": "020", "priority": "CRITICAL"},
        )
        self._exec_reader = ExecutionPlanReader()
        self._arch_reader = ArchitectureDecisionReader()
        self._tech_reader = TechnologySelectionReader()
        self._req_reader = RequirementNormalizationReader()
        self._cap_reader = ProjectCapabilityReader()
        self._folder_planner = FolderPlanner()
        self._file_planner = FilePlanner()
        self._validator = StructureValidator()
        self._cache = CacheManager(enabled=True)
        self._quality_gate = QualityGate()
        self._builder = BlueprintBuilder()

    def execute(self, context: GenerationContext) -> StageResult:
        try:
            _log.info("ProjectStructurePlanningEngine starting (Spec 020)")

            exec_data = self._exec_reader.read(context)
            arch_data = self._arch_reader.read(context)
            tech_data = self._tech_reader.read(context)
            req_data = self._req_reader.read(context)
            cap_data = self._cap_reader.read(context)

            sources_used, sources_missing = [], []
            for name, data in [
                (SOURCE_EXECUTION_PLAN, exec_data),
                (SOURCE_ARCHITECTURE_DECISION, arch_data),
                (SOURCE_TECHNOLOGY_SELECTION, tech_data),
                (SOURCE_NORMALIZED_REQUIREMENTS, req_data),
                (SOURCE_PROJECT_CAPABILITY, cap_data),
            ]:
                (sources_used if data.available else sources_missing).append(name)

            cache_key = self._cache.make_key(
                exec_data.raw, arch_data.raw, tech_data.raw, req_data.raw, cap_data.raw,
            )
            cached = self._cache.get(cache_key)
            if cached is not None:
                bp = ProjectStructureBlueprint(**{
                    k: v for k, v in cached.items()
                    if k in ProjectStructureBlueprint.__dataclass_fields__
                })
                bp.cache_info = self._cache.info_for_hit(cache_key)
                context.set("project_structure_blueprint", bp)
                return self.ok(outputs={"project_structure_blueprint": bp.to_dict()},
                               metadata={"cache": "hit"})

            root_name = "telegram_bot"
            if tech_data.available and tech_data.language:
                root_name = f"{tech_data.language.lower()}_telegram_bot"

            folders = self._folder_planner.plan(
                exec_data, arch_data, tech_data, cap_data, root_name=root_name,
            )
            files, modules = self._file_planner.plan(
                folders, exec_data, arch_data, tech_data, req_data, root_name=root_name,
            )

            # Build simple dependency list from file.depends_on
            dependencies: List[FileDependency] = []
            for f in files:
                for dep_id in f.depends_on:
                    dependencies.append(FileDependency(
                        from_file_id=dep_id,
                        to_file_id=f.file_id,
                        dependency_kind="import",
                        reason=f"Declared dependency of {f.name}",
                    ))

            conflicts = self._validator.validate(folders, files, dependencies)

            confidence = self._compute_confidence(sources_used, sources_missing, conflicts, files)

            bp = self._builder.build(
                root_name=root_name,
                folders=folders,
                files=files,
                modules=modules,
                dependencies=dependencies,
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
            context.set("project_structure_blueprint", bp)

            _log.info(
                "ProjectStructurePlanningEngine finished — verdict=%s folders=%d files=%d",
                verdict, len(folders), len(files),
            )

            if not passed:
                return self.failed(
                    errors=[f"Structure Blueprint failed quality gate (verdict={verdict})"],
                    outputs={"project_structure_blueprint": bp_dict},
                    warnings=[f.message for f in gate_findings],
                )
            return self.ok(
                outputs={"project_structure_blueprint": bp_dict},
                metadata={
                    "blueprint_id": bp.blueprint_id,
                    "verdict": verdict,
                    "folder_count": len(folders),
                    "file_count": len(files),
                    "confidence": confidence,
                },
            )
        except Exception as exc:
            _log.exception("ProjectStructurePlanningEngine crashed: %s", exc)
            return self.failed(errors=[f"ProjectStructurePlanningEngine error: {exc}"])

    def _compute_confidence(self, used, missing, conflicts, files) -> float:
        total = len(ALL_SOURCES)
        ratio = len(used) / total if total else 0.0
        crit = sum(1 for c in conflicts if getattr(c, "severity", "") == "critical")
        penalty = min(0.4, crit * 0.15)
        richness = min(1.0, len(files) / 20.0)
        conf = (0.5 * ratio) + (0.3 * richness) + 0.2 - penalty
        return round(max(0.0, min(1.0, conf)), 3)


__all__ = ["ProjectStructurePlanningEngine"]
