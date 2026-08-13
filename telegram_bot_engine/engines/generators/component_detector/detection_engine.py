"""
Component Detection Engine (Specification 007).

The :class:`ComponentDetectionEngine` is the engine responsible for
detecting **all** software components the generated Telegram bot
project will need **before** code generation begins.  It does **not**
write code, create files, build folders, or generate any project files.
Its sole function is to detect, classify, validate, and order every
software component.

Data source
-----------
The engine reads **only** three artefacts from the generation context:

1. ``project_blueprint`` — produced by the
   :class:`~telegram_bot_engine.engines.generators.project_planner.ProjectPlanningEngine`.
2. ``blueprint_validation_report`` — produced by the
   :class:`~telegram_bot_engine.engines.generators.blueprint_validator.BlueprintValidatorEngine`.
3. ``project_structure_map`` — produced by the
   :class:`~telegram_bot_engine.engines.generators.structure_generator.StructureGenerationEngine`.

It is **forbidden** from reading the user's request or the analysis
report.

Responsibility
--------------
* Scan the blueprint's components and the structure map's files to
  detect every software component.
* Classify each component by type (command, handler, service,
  repository, etc.).
* Resolve dependencies between detected components.
* Detect and merge duplicate components.
* Validate the Single Responsibility Principle for each component.
* Check scalability and compatibility.
* Validate quality rules (no unused, no self-dep, no circular deps).
* Compute the build order.
* Produce a :class:`ComponentRegistry` stored as the
  ``component_registry`` artefact.

What this engine does NOT do
----------------------------
* It does **not** write code inside files.
* It does **not** create databases.
* It does **not** build bot logic.
* It does **not** add components that are not in the blueprint or
  structure map.
* It does **not** read the user's request.

Output
------
The final output is a :class:`ComponentRegistry`, stored in the
context as the ``component_registry`` artefact.
"""

from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from ....core.context import GenerationContext
from ....core.result import StageResult
from ...base.base_engine import BaseEngine
from ..blueprint_validator.validation_report import (
    BlueprintValidationReport,
    STATUS_APPROVED,
    STATUS_REJECTED,
)
from ..project_planner.blueprint import ProjectBlueprint
from ..structure_generator.structure_map import ProjectStructureMap
from .build_order_computer import BuildOrderComputer
from .compatibility_checker import CompatibilityChecker
from .duplicate_detector import DuplicateDetector
from .quality_validator import QualityRulesValidator
from .relation_analyzer import RelationAnalyzer
from .registry import (
    ComponentRegistry,
    DetectionFinding,
    SEVERITY_ERROR,
    SEVERITY_WARNING,
)
from .responsibility_validator import ResponsibilityValidator
from .scalability_checker import ScalabilityChecker
from .type_detector import TypeDetector


class ComponentDetectionEngine(BaseEngine):
    """The engine that detects all software components for the project.

    This engine is the authority on *what* components the project will
    have.  It reads the ``project_blueprint``,
    ``blueprint_validation_report``, and ``project_structure_map``
    artefacts, detects every software component, validates them, and
    produces a :class:`ComponentRegistry` stored as the
    ``component_registry`` artefact.

    The engine is forbidden from reading the user's request or the
    analysis report.
    """

    def __init__(self) -> None:
        super().__init__(
            name="component_detector",
            version="1.0.0",
            description=(
                "Detects all software components the project will need "
                "before code generation begins.  Reads the Project "
                "Blueprint, Blueprint Validation Report, and Project "
                "Structure Map.  Produces a Component Registry "
                "artefact.  Does not write code, create files, or "
                "generate project files."
            ),
            tags=["generation", "detection", "components"],
            metadata={"phase": "detect_components"},
        )
        self._type_detector = TypeDetector()
        self._relation_analyzer = RelationAnalyzer()
        self._duplicate_detector = DuplicateDetector()
        self._responsibility_validator = ResponsibilityValidator()
        self._scalability_checker = ScalabilityChecker()
        self._compatibility_checker = CompatibilityChecker()
        self._quality_validator = QualityRulesValidator()
        self._build_order_computer = BuildOrderComputer()

    # -----------------------------------------------------------------#
    # Main entry point
    # -----------------------------------------------------------------#

    def execute(self, context: GenerationContext) -> StageResult:
        """Detect all components and produce the Component Registry.

        Steps:
            1. Obtain the blueprint, validation report, and structure
               map from the context.
            2. Scan and classify all components (type detection).
            3. Resolve dependencies (relation analysis).
            4. Detect and merge duplicates.
            5. Validate the Single Responsibility Principle.
            6. Check scalability and compatibility.
            7. Validate quality rules (no unused, no self-dep, no
               cycles).
            8. Compute the build order.
            9. Assemble the Component Registry.
            10. Store the registry in the context.
        """
        gen_start = time.perf_counter()

        # Step 1: obtain the three artefacts.
        blueprint = context.get("project_blueprint")
        if blueprint is None:
            return self.failed([
                "No 'project_blueprint' artefact found. The Component "
                "Detection Engine requires the Project Planning Engine "
                "to have run first. The detection engine does not "
                "read the raw request."
            ])

        validation_report = context.get("blueprint_validation_report")
        if validation_report is None:
            return self.failed([
                "No 'blueprint_validation_report' artefact found. The "
                "Component Detection Engine requires the Blueprint "
                "Validator Engine to have run first."
            ])

        structure_map = context.get("project_structure_map")
        if structure_map is None:
            return self.failed([
                "No 'project_structure_map' artefact found. The "
                "Component Detection Engine requires the Structure "
                "Generation Engine to have run first."
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

        validation_status = (
            validation_report.status
            if isinstance(validation_report, BlueprintValidationReport)
            else "unknown"
        )

        self._log.info(
            "Starting component detection",
            {
                "blueprint_name": blueprint.identity.name,
                "blueprint_components": len(blueprint.components),
                "features": len(blueprint.features),
                "structure_files": len(structure_map.files),
                "validation_status": validation_status,
            },
        )

        # Step 2: scan and classify all components.
        components = self._type_detector.detect(blueprint, structure_map)
        self._log.info(
            "Type detection complete",
            {"detected_components": len(components)},
        )

        # Step 3: resolve dependencies.
        edges, relation_warnings = self._relation_analyzer.analyze(components)
        self._log.info(
            "Relation analysis complete",
            {
                "edges": len(edges),
                "relation_warnings": len(relation_warnings),
            },
        )

        # Step 4: detect and merge duplicates.
        components, dup_findings = self._duplicate_detector.detect(components)
        self._log.info(
            "Duplicate detection complete",
            {
                "final_components": len(components),
                "merges": len(dup_findings),
            },
        )

        # Re-resolve relations after deduplication (reverse links may
        # have changed).
        edges, relation_warnings = self._relation_analyzer.analyze(components)

        # Step 5: validate the Single Responsibility Principle.
        resp_findings = self._responsibility_validator.validate(components)
        self._log.info(
            "Responsibility validation complete",
            {"findings": len(resp_findings)},
        )

        # Step 6: check scalability and compatibility.
        scale_findings = self._scalability_checker.check(components)
        compat_findings = self._compatibility_checker.check(components, blueprint)
        self._log.info(
            "Scalability and compatibility checks complete",
            {
                "scalability_findings": len(scale_findings),
                "compatibility_findings": len(compat_findings),
            },
        )

        # Step 7: validate quality rules.
        quality_findings = self._quality_validator.validate(components)
        self._log.info(
            "Quality validation complete",
            {"findings": len(quality_findings)},
        )

        # Step 8: compute the build order.
        build_order = self._build_order_computer.compute(components)
        self._log.info(
            "Build order computed",
            {"entries": len(build_order)},
        )

        # Step 9: assemble the Component Registry.
        all_findings: List[DetectionFinding] = []
        all_findings.extend(dup_findings)
        all_findings.extend(resp_findings)
        all_findings.extend(scale_findings)
        all_findings.extend(compat_findings)
        all_findings.extend(quality_findings)

        # Collect warnings from the relation analyzer.
        for w in relation_warnings:
            all_findings.append(DetectionFinding(
                severity=SEVERITY_WARNING,
                code="dangling_dependency",
                message=w,
                affected="",
            ))

        # Check for error-level findings.
        error_findings = [f for f in all_findings if f.severity == SEVERITY_ERROR]
        warning_findings = [
            f for f in all_findings if f.severity == SEVERITY_WARNING
        ]

        total_duration_ms = (time.perf_counter() - gen_start) * 1000

        registry = ComponentRegistry(
            project_name=blueprint.identity.name or structure_map.project_name,
            root_path=structure_map.root_path,
            components=components,
            relationships=edges,
            build_order=build_order,
            source_blueprint=blueprint.identity.name or "unnamed",
            validation_status=validation_status,
            source_structure_map=structure_map.project_name,
            findings=all_findings,
            summary=self._build_summary(
                len(components), len(edges), len(build_order),
                len(error_findings), len(warning_findings),
                total_duration_ms,
            ),
            notes=[
                f"Component registry generated at "
                f"{datetime.now(timezone.utc).isoformat()}.",
                f"Source blueprint: {blueprint.identity.name or 'unnamed'}.",
                f"Source structure map: {structure_map.project_name}.",
                f"Validation status: {validation_status}.",
            ],
            warnings=[
                f.message for f in warning_findings
            ],
        )

        # Step 10: store the registry in the context.
        context.set("component_registry", registry)
        context.metadata["component_registry"] = registry

        self._log.info(
            "Component detection complete",
            {
                "project_name": registry.project_name,
                "components": registry.component_count,
                "relationships": len(registry.relationships),
                "build_order_entries": len(registry.build_order),
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
                outputs={"component_registry": registry},
                warnings=registry.warnings,
            )

        return self.ok(
            outputs={"component_registry": registry},
            metadata={
                "project_name": registry.project_name,
                "component_count": registry.component_count,
                "relationship_count": len(registry.relationships),
                "build_order_entries": len(registry.build_order),
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
        component_count: int,
        edge_count: int,
        build_order_count: int,
        error_count: int,
        warning_count: int,
        duration_ms: float,
    ) -> str:
        """Build a human-readable summary of the component registry."""
        return (
            f"Detected {component_count} component(s) with "
            f"{edge_count} relationship(s) and "
            f"{build_order_count} build-order entries. "
            f"{error_count} error(s), {warning_count} warning(s). "
            f"Generated in {round(duration_ms, 2)} ms."
        )


__all__ = ["ComponentDetectionEngine"]
