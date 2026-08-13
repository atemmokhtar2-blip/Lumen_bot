"""
Dependency Resolution Engine (Specification 009).

The :class:`DependencyResolutionEngine` is the engine responsible for
building the complete, authoritative dependency map for the generated
Telegram bot project **before** any code is written or any file is
created on disk.  It does **not** write code, create files, install
libraries, or add dependencies.  Its sole function is to analyse the
project's components and structure and produce a complete, validated
:class:`DependencyResolutionReport` — the authoritative dependency
map for every library, framework, and tool the project will use.

Data source
-----------
The engine reads **only** five artefacts from the generation context:

1. ``project_blueprint`` — produced by the
   :class:`~telegram_bot_engine.engines.generators.project_planner.ProjectPlanningEngine`.
2. ``blueprint_validation_report`` — produced by the
   :class:`~telegram_bot_engine.engines.generators.blueprint_validator.BlueprintValidatorEngine`.
3. ``project_structure_map`` — produced by the
   :class:`~telegram_bot_engine.engines.generators.structure_generator.StructureGenerationEngine`.
4. ``component_registry`` — produced by the
   :class:`~telegram_bot_engine.engines.generators.component_detector.ComponentDetectionEngine`.
5. ``file_generation_plan`` — produced by the
   :class:`~telegram_bot_engine.engines.generators.file_planner.FileGenerationPlanningEngine`.

It is **forbidden** from reading the user's request.

Responsibility
--------------
* Analyse all detected components and determine their required
  libraries, frameworks, and tools.
* Determine the required dependencies (with versions, reasons,
  sources, and priorities).
* Build the complete dependency graph (relationships, load order).
* Check compatibility (language, framework, OS, inter-library).
* Detect conflicts (version conflicts, duplicates, unused
  dependencies, circular dependencies, broken dependencies).
* Optimise the dependency list (minimise, prefer official, avoid
  abandoned/unstable).
* Flag security risks (bad reputation, untrusted, known-vulnerable
  versions).
* Validate the report (all deps complete, no conflicts, valid
  relationships, buildable).
* Produce a :class:`DependencyResolutionReport` stored as the
  ``dependency_resolution_report`` artefact.

What this engine does NOT do
----------------------------
* It does **not** write code.
* It does **not** create files on disk.
* It does **not** install libraries.
* It does **not** add dependencies to the project.
* It does **not** read the user's request.

Output
------
The final output is a :class:`DependencyResolutionReport`, stored in
the context as the ``dependency_resolution_report`` artefact.
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
from ..file_planner.plan_data import FileGenerationPlan
from ..project_planner.blueprint import ProjectBlueprint
from ..structure_generator.structure_map import ProjectStructureMap
from .component_analyzer import ComponentAnalyzer
from .compatibility_checker import CompatibilityChecker
from .conflict_detector import ConflictDetector
from .dependency_graph_builder import DependencyGraphBuilder
from .library_determiner import LibraryDeterminer
from .optimizer import DependencyOptimizer
from .plan_validator import PlanValidator
from .report_data import (
    DependencyResolutionReport,
    ResolutionFinding,
    SEVERITY_ERROR,
    SEVERITY_WARNING,
)
from .security_checker import SecurityChecker


class DependencyResolutionEngine(BaseEngine):
    """The engine that builds the complete dependency map for the project.

    This engine is the authority on *which* dependencies the project
    will use, *in what versions*, and *in what order* they should be
    resolved.  It reads the ``project_blueprint``,
    ``blueprint_validation_report``, ``project_structure_map``,
    ``component_registry``, and ``file_generation_plan`` artefacts,
    analyses all components, determines the required dependencies,
    builds the dependency graph, checks compatibility, detects
    conflicts, optimises the list, flags security risks, validates
    the report, and produces a :class:`DependencyResolutionReport`
    stored as the ``dependency_resolution_report`` artefact.

    The engine is forbidden from reading the user's request.
    """

    def __init__(self) -> None:
        super().__init__(
            name="dependency_resolver",
            version="1.0.0",
            description=(
                "Builds the complete dependency map for the "
                "project before construction begins.  Reads the "
                "Project Blueprint, Blueprint Validation Report, "
                "Project Structure Map, Component Registry, and "
                "File Generation Plan.  Produces a Dependency "
                "Resolution Report artefact.  Does not write "
                "code, create files, install libraries, or add "
                "dependencies."
            ),
            tags=["generation", "dependencies", "resolution"],
            metadata={"phase": "resolve_dependencies"},
        )
        self._component_analyzer = ComponentAnalyzer()
        self._library_determiner = LibraryDeterminer()
        self._graph_builder = DependencyGraphBuilder()
        self._compatibility_checker = CompatibilityChecker()
        self._conflict_detector = ConflictDetector()
        self._optimizer = DependencyOptimizer()
        self._security_checker = SecurityChecker()
        self._plan_validator = PlanValidator()

    # -----------------------------------------------------------------#
    # Main entry point
    # -----------------------------------------------------------------#

    def execute(self, context: GenerationContext) -> StageResult:
        """Build the dependency map and produce the resolution report.

        Steps:
            1. Obtain the five artefacts from the context.
            2. Analyse all components and determine their required
               libraries.
            3. Determine the required dependencies and their metadata.
            4. Build the dependency graph (relationships, load order).
            5. Check compatibility (language, framework, OS,
               inter-library).
            6. Detect conflicts (duplicates, version conflicts, unused,
               broken, circular, orphaned).
            7. Optimise the dependency list (minimise, prefer
               official, avoid abandoned/unstable).
            8. Flag security risks (bad reputation, untrusted,
               known-vulnerable versions).
            9. Assemble the preliminary report.
            10. Validate the report.
            11. Store the report in the context.
        """
        gen_start = time.perf_counter()

        # Step 1: obtain the five artefacts.
        blueprint = context.get("project_blueprint")
        if blueprint is None:
            return self.failed([
                "No 'project_blueprint' artefact found. The "
                "Dependency Resolution Engine requires the Project "
                "Planning Engine to have run first. The resolution "
                "engine does not read the raw request."
            ])

        validation_report = context.get("blueprint_validation_report")
        if validation_report is None:
            return self.failed([
                "No 'blueprint_validation_report' artefact found. "
                "The Dependency Resolution Engine requires the "
                "Blueprint Validator Engine to have run first."
            ])

        structure_map = context.get("project_structure_map")
        if structure_map is None:
            return self.failed([
                "No 'project_structure_map' artefact found. The "
                "Dependency Resolution Engine requires the "
                "Structure Generation Engine to have run first."
            ])

        registry = context.get("component_registry")
        if registry is None:
            return self.failed([
                "No 'component_registry' artefact found. The "
                "Dependency Resolution Engine requires the "
                "Component Detection Engine to have run first."
            ])

        file_plan = context.get("file_generation_plan")
        if file_plan is None:
            return self.failed([
                "No 'file_generation_plan' artefact found. The "
                "Dependency Resolution Engine requires the File "
                "Generation Planning Engine to have run first."
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
        if not isinstance(file_plan, FileGenerationPlan):
            return self.failed([
                "The 'file_generation_plan' artefact is not a "
                "FileGenerationPlan instance."
            ])

        validation_status = (
            validation_report.status
            if isinstance(validation_report, BlueprintValidationReport)
            else "unknown"
        )

        self._log.info(
            "Starting dependency resolution",
            {
                "blueprint_name": blueprint.identity.name,
                "components": registry.component_count,
                "structure_files": len(structure_map.files),
                "file_plan_files": file_plan.file_count,
                "validation_status": validation_status,
            },
        )

        # Step 2: analyse all components and determine their required
        # libraries.
        analysis = self._component_analyzer.analyze(
            registry, structure_map, file_plan,
        )
        missing_requirements_findings = (
            self._component_analyzer.findings_for_missing_requirements(
                analysis,
            )
        )
        self._log.info(
            "Component analysis complete",
            {
                "components_analysed": analysis.component_count,
                "components_without_requirements": len(
                    analysis.components_without_requirements,
                ),
                "required_libraries": len(
                    analysis.all_required_libraries,
                ),
            },
        )

        # Step 3: determine the required dependencies and their
        # metadata.
        dependencies = self._library_determiner.determine(
            analysis, blueprint, structure_map, file_plan, registry,
        )
        self._log.info(
            "Library determination complete",
            {"resolved_dependencies": len(dependencies)},
        )

        # Step 4: build the dependency graph (relationships, load
        # order).
        relationships, load_order, graph_warnings = (
            self._graph_builder.build(dependencies, registry)
        )
        self._log.info(
            "Dependency graph built",
            {
                "relationships": len(relationships),
                "load_order_entries": len(load_order),
                "graph_warnings": len(graph_warnings),
            },
        )

        # Step 5: check compatibility.
        compatibility_findings = self._compatibility_checker.check(
            dependencies, relationships, blueprint,
        )
        self._log.info(
            "Compatibility check complete",
            {"compatibility_findings": len(compatibility_findings)},
        )

        # Step 6: detect conflicts.
        conflict_findings = self._conflict_detector.detect(
            dependencies, relationships,
        )
        self._log.info(
            "Conflict detection complete",
            {"conflicts": len(conflict_findings)},
        )

        # Step 7: optimise the dependency list.
        optimization_findings = self._optimizer.optimize(dependencies)
        self._log.info(
            "Optimization complete",
            {"optimization_findings": len(optimization_findings)},
        )

        # Step 8: flag security risks.
        security_findings = self._security_checker.check(dependencies)
        self._log.info(
            "Security check complete",
            {"security_findings": len(security_findings)},
        )

        # Step 9: assemble the preliminary report.
        all_findings: List[ResolutionFinding] = []
        all_findings.extend(missing_requirements_findings)
        all_findings.extend(compatibility_findings)
        all_findings.extend(conflict_findings)
        all_findings.extend(optimization_findings)
        all_findings.extend(security_findings)

        # Convert graph warnings to findings.
        for w in graph_warnings:
            all_findings.append(ResolutionFinding(
                severity=SEVERITY_WARNING,
                code="graph_warning",
                message=w,
                affected="",
                category="validation",
            ))

        report = DependencyResolutionReport(
            project_name=(
                blueprint.identity.name or structure_map.project_name
            ),
            language=blueprint.identity.language,
            language_version=blueprint.identity.language_version,
            framework=blueprint.identity.framework,
            dependencies=dependencies,
            relationships=relationships,
            load_order=load_order,
            source_blueprint=blueprint.identity.name or "unnamed",
            validation_status=validation_status,
            source_structure_map=structure_map.project_name,
            source_component_registry=registry.project_name,
            source_file_generation_plan=file_plan.project_name,
            findings=all_findings,
            summary="",
            notes=[
                f"Dependency resolution report generated at "
                f"{datetime.now(timezone.utc).isoformat()}.",
                f"Source blueprint: "
                f"{blueprint.identity.name or 'unnamed'}.",
                f"Source structure map: {structure_map.project_name}.",
                f"Source component registry: "
                f"{registry.project_name}.",
                f"Source file generation plan: "
                f"{file_plan.project_name}.",
                f"Validation status: {validation_status}.",
            ],
            warnings=[],
        )

        # Step 10: validate the report.
        validation_findings = self._plan_validator.validate(
            report, registry,
        )
        all_findings.extend(validation_findings)
        self._log.info(
            "Plan validation complete",
            {"validation_findings": len(validation_findings)},
        )

        # Separate errors and warnings.
        error_findings = [
            f for f in all_findings if f.severity == SEVERITY_ERROR
        ]
        warning_findings = [
            f for f in all_findings if f.severity == SEVERITY_WARNING
        ]

        total_duration_ms = (time.perf_counter() - gen_start) * 1000

        # Finalise the report.
        report.findings = all_findings
        report.warnings = [f.message for f in warning_findings]
        report.summary = self._build_summary(
            len(dependencies), len(relationships), len(load_order),
            len(error_findings), len(warning_findings),
            total_duration_ms,
        )

        # Step 11: store the report in the context.
        context.set("dependency_resolution_report", report)
        context.metadata["dependency_resolution_report"] = report

        self._log.info(
            "Dependency resolution complete",
            {
                "project_name": report.project_name,
                "dependencies": report.dependency_count,
                "relationships": len(report.relationships),
                "load_order_entries": len(report.load_order),
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
                outputs={"dependency_resolution_report": report},
                warnings=report.warnings,
            )

        return self.ok(
            outputs={"dependency_resolution_report": report},
            metadata={
                "project_name": report.project_name,
                "dependency_count": report.dependency_count,
                "relationship_count": len(report.relationships),
                "load_order_entries": len(report.load_order),
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
        dependency_count: int,
        relationship_count: int,
        order_count: int,
        error_count: int,
        warning_count: int,
        duration_ms: float,
    ) -> str:
        """Build a human-readable summary of the resolution report."""
        return (
            f"Resolved {dependency_count} dependency(ies) with "
            f"{relationship_count} relationship(s) and "
            f"{order_count} load-order entries. "
            f"{error_count} error(s), {warning_count} warning(s). "
            f"Generated in {round(duration_ms, 2)} ms."
        )


__all__ = ["DependencyResolutionEngine"]
