"""
File Generation Planning Engine (Specification 008).

The :class:`FileGenerationPlanningEngine` is the engine responsible for
planning **all** files the generated Telegram bot project will contain
**before** any file is created on disk.  It does **not** write code,
create files, build folders, or generate any project files.  Its sole
function is to analyse the project's components and structure map and
produce a complete, validated :class:`FileGenerationPlan` — the
authoritative plan for every file the project will contain.

Data source
-----------
The engine reads **only** four artefacts from the generation context:

1. ``project_blueprint`` — produced by the
   :class:`~telegram_bot_engine.engines.generators.project_planner.ProjectPlanningEngine`.
2. ``blueprint_validation_report`` — produced by the
   :class:`~telegram_bot_engine.engines.generators.blueprint_validator.BlueprintValidatorEngine`.
3. ``project_structure_map`` — produced by the
   :class:`~telegram_bot_engine.engines.generators.structure_generator.StructureGenerationEngine`.
4. ``component_registry`` — produced by the
   :class:`~telegram_bot_engine.engines.generators.component_detector.ComponentDetectionEngine`.

It is **forbidden** from reading the user's request.

Responsibility
--------------
* Analyse all detected components and group their files.
* Determine the required files per component and assign metadata.
* Determine the relationships and dependencies between files.
* Compute the generation order (topological sort).
* Detect conflicts (duplicates, naming conflicts, useless files,
  unlinked files, dangling/circular dependencies).
* Validate the plan (all components have files, all files have
  purpose, all relationships valid, generation order valid).
* Produce a :class:`FileGenerationPlan` stored as the
  ``file_generation_plan`` artefact.

What this engine does NOT do
----------------------------
* It does **not** write code inside files.
* It does **not** create files on disk.
* It does **not** build folders.
* It does **not** generate any project files.
* It does **not** read the user's request.

Output
------
The final output is a :class:`FileGenerationPlan`, stored in the
context as the ``file_generation_plan`` artefact.
"""

from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Any, Dict, List

from ....core.context import GenerationContext
from ....core.result import StageResult
from ...base.base_engine import BaseEngine
from ..blueprint_validator.validation_report import (
    BlueprintValidationReport,
    STATUS_APPROVED,
)
from ..component_detector.registry import ComponentRegistry
from ..project_planner.blueprint import ProjectBlueprint
from ..structure_generator.structure_map import ProjectStructureMap
from .component_analyzer import ComponentAnalyzer
from .conflict_detector import ConflictDetector
from .file_determiner import FileDeterminer
from .generation_order_computer import GenerationOrderComputer
from .plan_data import (
    FileGenerationPlan,
    PlanFinding,
    SEVERITY_ERROR,
    SEVERITY_WARNING,
)
from .plan_validator import PlanValidator
from .relationship_resolver import RelationshipResolver


class FileGenerationPlanningEngine(BaseEngine):
    """The engine that plans all files for the project.

    This engine is the authority on *which* files the project will have
    and *in what order* they should be created.  It reads the
    ``project_blueprint``, ``blueprint_validation_report``,
    ``project_structure_map``, and ``component_registry`` artefacts,
    analyses all components, determines the required files, resolves
    their relationships, computes the generation order, detects
    conflicts, validates the plan, and produces a
    :class:`FileGenerationPlan` stored as the
    ``file_generation_plan`` artefact.

    The engine is forbidden from reading the user's request.
    """

    def __init__(self) -> None:
        super().__init__(
            name="file_planner",
            version="1.0.0",
            description=(
                "Plans all files the project will contain before "
                "any file is created on disk.  Reads the Project "
                "Blueprint, Blueprint Validation Report, Project "
                "Structure Map, and Component Registry.  Produces "
                "a File Generation Plan artefact.  Does not write "
                "code, create files, or generate project files."
            ),
            tags=["generation", "planning", "files"],
            metadata={"phase": "plan_files"},
        )
        self._component_analyzer = ComponentAnalyzer()
        self._file_determiner = FileDeterminer()
        self._relationship_resolver = RelationshipResolver()
        self._generation_order_computer = GenerationOrderComputer()
        self._conflict_detector = ConflictDetector()
        self._plan_validator = PlanValidator()

    # -----------------------------------------------------------------#
    # Main entry point
    # -----------------------------------------------------------------#

    def execute(self, context: GenerationContext) -> StageResult:
        """Plan all files and produce the File Generation Plan.

        Steps:
            1. Obtain the blueprint, validation report, structure map,
               and component registry from the context.
            2. Analyse all components and group their files.
            3. Determine the required files and their metadata.
            4. Resolve the relationships and dependencies between
               files.
            5. Compute the generation order (topological sort).
            6. Detect conflicts (duplicates, naming conflicts, useless
               files, unlinked files, dangling/circular dependencies).
            7. Validate the plan.
            8. Assemble the File Generation Plan.
            9. Store the plan in the context.
        """
        gen_start = time.perf_counter()

        # Step 1: obtain the four artefacts.
        blueprint = context.get("project_blueprint")
        if blueprint is None:
            return self.failed([
                "No 'project_blueprint' artefact found. The File "
                "Generation Planning Engine requires the Project "
                "Planning Engine to have run first. The planning "
                "engine does not read the raw request."
            ])

        validation_report = context.get("blueprint_validation_report")
        if validation_report is None:
            return self.failed([
                "No 'blueprint_validation_report' artefact found. "
                "The File Generation Planning Engine requires the "
                "Blueprint Validator Engine to have run first."
            ])

        structure_map = context.get("project_structure_map")
        if structure_map is None:
            return self.failed([
                "No 'project_structure_map' artefact found. The "
                "File Generation Planning Engine requires the "
                "Structure Generation Engine to have run first."
            ])

        registry = context.get("component_registry")
        if registry is None:
            return self.failed([
                "No 'component_registry' artefact found. The File "
                "Generation Planning Engine requires the Component "
                "Detection Engine to have run first."
            ])

        # Type-check the artefacts.
        if not isinstance(blueprint, ProjectBlueprint):
            return self.failed([
                "The 'project_blueprint' artefact is not a "
                "ProjectBlueprint instance."
            ])
        if not isinstance(structure_map, ProjectStructureMap):
            return self.failed([
                "The 'project_structure_map' artefact is not a "
                "ProjectStructureMap instance."
            ])
        if not isinstance(registry, ComponentRegistry):
            return self.failed([
                "The 'component_registry' artefact is not a "
                "ComponentRegistry instance."
            ])

        validation_status = (
            validation_report.status
            if isinstance(validation_report, BlueprintValidationReport)
            else "unknown"
        )

        self._log.info(
            "Starting file generation planning",
            {
                "blueprint_name": blueprint.identity.name,
                "components": registry.component_count,
                "structure_files": len(structure_map.files),
                "validation_status": validation_status,
            },
        )

        # Step 2: analyse all components and group their files.
        analysis = self._component_analyzer.analyze(registry, structure_map)
        missing_file_findings = (
            self._component_analyzer.findings_for_missing_files(analysis)
        )
        self._log.info(
            "Component analysis complete",
            {
                "components_analysed": analysis.component_count,
                "components_without_files": len(
                    analysis.components_without_files
                ),
            },
        )

        # Step 3: determine the required files and their metadata.
        files = self._file_determiner.determine(analysis, structure_map)
        self._log.info(
            "File determination complete",
            {"planned_files": len(files)},
        )

        # Step 4: resolve the relationships and dependencies.
        relationships, rel_warnings = self._relationship_resolver.resolve(
            files, registry,
        )
        self._log.info(
            "Relationship resolution complete",
            {
                "relationships": len(relationships),
                "relation_warnings": len(rel_warnings),
            },
        )

        # Step 5: compute the generation order.
        generation_order = self._generation_order_computer.compute(files)
        self._log.info(
            "Generation order computed",
            {"order_entries": len(generation_order)},
        )

        # Step 6: detect conflicts.
        conflict_findings = self._conflict_detector.detect(
            files, relationships,
        )
        self._log.info(
            "Conflict detection complete",
            {"conflicts": len(conflict_findings)},
        )

        # Step 7: assemble the preliminary plan for validation.
        all_findings: List[PlanFinding] = []
        all_findings.extend(missing_file_findings)
        all_findings.extend(conflict_findings)

        # Convert relation warnings to findings.
        for w in rel_warnings:
            all_findings.append(PlanFinding(
                severity=SEVERITY_WARNING,
                code="dangling_file_dependency",
                message=w,
                affected="",
            ))

        plan = FileGenerationPlan(
            project_name=blueprint.identity.name or structure_map.project_name,
            root_path=structure_map.root_path,
            files=files,
            relationships=relationships,
            generation_order=generation_order,
            source_blueprint=blueprint.identity.name or "unnamed",
            validation_status=validation_status,
            source_structure_map=structure_map.project_name,
            source_component_registry=registry.project_name,
            findings=all_findings,
            summary="",
            notes=[
                f"File generation plan generated at "
                f"{datetime.now(timezone.utc).isoformat()}.",
                f"Source blueprint: {blueprint.identity.name or 'unnamed'}.",
                f"Source structure map: {structure_map.project_name}.",
                f"Source component registry: {registry.project_name}.",
                f"Validation status: {validation_status}.",
            ],
            warnings=[],
        )

        # Step 8: validate the plan.
        validation_findings = self._plan_validator.validate(
            plan, registry, structure_map,
        )
        all_findings.extend(validation_findings)
        self._log.info(
            "Plan validation complete",
            {"validation_findings": len(validation_findings)},
        )

        # Separate errors and warnings.
        error_findings = [f for f in all_findings if f.severity == SEVERITY_ERROR]
        warning_findings = [
            f for f in all_findings if f.severity == SEVERITY_WARNING
        ]

        total_duration_ms = (time.perf_counter() - gen_start) * 1000

        # Finalise the plan.
        plan.findings = all_findings
        plan.warnings = [f.message for f in warning_findings]
        plan.summary = self._build_summary(
            len(files), len(relationships), len(generation_order),
            len(error_findings), len(warning_findings),
            total_duration_ms,
        )

        # Step 9: store the plan in the context.
        context.set("file_generation_plan", plan)
        context.metadata["file_generation_plan"] = plan

        self._log.info(
            "File generation planning complete",
            {
                "project_name": plan.project_name,
                "files": plan.file_count,
                "relationships": len(plan.relationships),
                "generation_order_entries": len(plan.generation_order),
                "errors": len(error_findings),
                "warnings": len(warning_findings),
                "duration_ms": round(total_duration_ms, 2),
            },
        )

        if error_findings:
            error_messages = [
                f"[{f.code}] {f.message}"
                for f in error_findings
            ]
            return self.failed(
                errors=error_messages,
                outputs={"file_generation_plan": plan},
                warnings=plan.warnings,
            )

        return self.ok(
            outputs={"file_generation_plan": plan},
            metadata={
                "project_name": plan.project_name,
                "file_count": plan.file_count,
                "relationship_count": len(plan.relationships),
                "generation_order_entries": len(plan.generation_order),
                "findings": len(all_findings),
                "errors": len(error_findings),
                "warnings": len(warning_findings),
                "duration_ms": round(total_duration_ms, 2),
            },
        )

    # -----------------------------------------------------------------#
    # Helpers
    # -----------------------------------------------------------------#

    @staticmethod
    def _build_summary(
        file_count: int,
        relationship_count: int,
        order_count: int,
        error_count: int,
        warning_count: int,
        duration_ms: float,
    ) -> str:
        """Build a human-readable summary of the file generation plan."""
        return (
            f"Planned {file_count} file(s) with "
            f"{relationship_count} relationship(s) and "
            f"{order_count} generation-order entries. "
            f"{error_count} error(s), {warning_count} warning(s). "
            f"Generated in {round(duration_ms, 2)} ms."
        )


__all__ = ["FileGenerationPlanningEngine"]
