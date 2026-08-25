"""
Plan Validator — validates the file generation plan (Specification 008).

The :class:`PlanValidator` is a stateless helper that the
:class:`FileGenerationPlanningEngine` calls during the *validation*
phase.  It performs the final validation checks on the complete
:class:`FileGenerationPlan`:

1. **All components have files.**  Every detected component in the
   component registry must have at least one planned file.
2. **All files have a clear purpose.**  Every planned file must have
   a non-empty purpose.
3. **All files have a responsible engine.**  Every planned file must
   have a non-empty responsible engine.
4. **All files have a folder.**  Every planned file must belong to a
   folder that exists in the structure map.
5. **All files have a source component (or are project-level).**  Every
   planned file must be linked to a detected component, or be a
   project-level file (e.g. README, Dockerfile, requirements).
6. **All relationships are valid.**  Every relationship's source and
   target must exist in the plan.
7. **The generation order is valid.**  The generation order must
   contain every file exactly once, in a topologically valid sequence.
8. **The plan is not empty.**  The plan must contain at least one file.

The validator does **not** modify the plan — it only records findings.

Data source
-----------
The validator reads **only** the :class:`FileGenerationPlan` and the
:class:`ComponentRegistry`.  It does **not** read the user's request.
"""

from __future__ import annotations

from typing import Dict, List, Set

from ..component_detector.registry import ComponentRegistry
from ..structure_generator.structure_map import ProjectStructureMap
from .plan_data import (
    FileGenerationPlan,
    PlanFinding,
    SEVERITY_ERROR,
    SEVERITY_WARNING,
)


class PlanValidator:
    """Stateless helper that validates the file generation plan.

    The validator is called by the
    :class:`FileGenerationPlanningEngine` after all other helpers have
    run.  It performs the final validation checks on the complete
    plan.
    """

    def validate(
        self,
        plan: FileGenerationPlan,
        registry: ComponentRegistry,
        structure_map: ProjectStructureMap,
    ) -> List[PlanFinding]:
        """Validate the file generation plan.

        Parameters:
            plan: The file generation plan to validate.
            registry: The component registry (for checking that all
                components have files).
            structure_map: The project structure map (for checking
                that all file folders exist).

        Returns:
            A list of :class:`PlanFinding` objects describing all
            validation issues found.
        """
        findings: List[PlanFinding] = []

        findings.extend(self._check_not_empty(plan))
        findings.extend(self._check_all_components_have_files(plan, registry))
        findings.extend(self._check_all_files_have_purpose(plan))
        findings.extend(self._check_all_files_have_engine(plan))
        findings.extend(self._check_all_files_have_folder(plan, structure_map))
        findings.extend(self._check_all_files_have_component(plan))
        findings.extend(self._check_all_relationships_valid(plan))
        findings.extend(self._check_generation_order_valid(plan))

        return findings

    # -----------------------------------------------------------------#
    # Validation checks
    # -----------------------------------------------------------------#

    @staticmethod
    def _check_not_empty(
        plan: FileGenerationPlan,
    ) -> List[PlanFinding]:
        """Check that the plan is not empty."""
        findings: List[PlanFinding] = []
        if plan.is_empty:
            findings.append(PlanFinding(
                severity=SEVERITY_ERROR,
                code="empty_plan",
                message=(
                    "The file generation plan is empty — it contains "
                    "no files.  At least one file must be planned."
                ),
                affected="",
                resolution_hint=(
                    "Ensure the structure map contains files and the "
                    "component registry contains components."
                ),
            ))
        return findings

    @staticmethod
    def _check_all_components_have_files(
        plan: FileGenerationPlan,
        registry: ComponentRegistry,
    ) -> List[PlanFinding]:
        """Check that every component in the registry has at least one file."""
        findings: List[PlanFinding] = []

        # Collect all component names that have files in the plan.
        components_with_files: Set[str] = set()
        for f in plan.files:
            if f.source_component:
                components_with_files.add(f.source_component)

        for comp in registry.components:
            if comp.name not in components_with_files:
                findings.append(PlanFinding(
                    severity=SEVERITY_WARNING,
                    code="component_without_files",
                    message=(
                        f"Component '{comp.name}' has no planned "
                        f"files.  Every component should have at "
                        f"least one file."
                    ),
                    affected=comp.name,
                    resolution_hint=(
                        f"Ensure the structure map includes at least "
                        f"one file for component '{comp.name}'."
                    ),
                ))

        return findings

    @staticmethod
    def _check_all_files_have_purpose(
        plan: FileGenerationPlan,
    ) -> List[PlanFinding]:
        """Check that every file has a clear purpose."""
        findings: List[PlanFinding] = []
        for f in plan.files:
            if not f.purpose:
                findings.append(PlanFinding(
                    severity=SEVERITY_ERROR,
                    code="file_without_purpose",
                    message=(
                        f"File '{f.path}' has no purpose.  Every "
                        f"file must have a clear purpose."
                    ),
                    affected=f.path,
                    resolution_hint=(
                        f"Assign a purpose to '{f.name}'."
                    ),
                ))
        return findings

    @staticmethod
    def _check_all_files_have_engine(
        plan: FileGenerationPlan,
    ) -> List[PlanFinding]:
        """Check that every file has a responsible engine."""
        findings: List[PlanFinding] = []
        for f in plan.files:
            if not f.responsible_engine:
                findings.append(PlanFinding(
                    severity=SEVERITY_ERROR,
                    code="file_without_engine",
                    message=(
                        f"File '{f.path}' has no responsible engine. "
                        f"Every file must have a responsible engine."
                    ),
                    affected=f.path,
                    resolution_hint=(
                        f"Assign a responsible engine to '{f.name}'."
                    ),
                ))
        return findings

    @staticmethod
    def _check_all_files_have_folder(
        plan: FileGenerationPlan,
        structure_map: ProjectStructureMap,
    ) -> List[PlanFinding]:
        """Check that every file belongs to a folder in the structure map."""
        findings: List[PlanFinding] = []

        folder_paths: Set[str] = {f.path for f in structure_map.folders}

        for f in plan.files:
            # Root-level files (empty folder) are acceptable.
            if not f.folder:
                continue

            if f.folder not in folder_paths:
                findings.append(PlanFinding(
                    severity=SEVERITY_WARNING,
                    code="file_folder_not_in_map",
                    message=(
                        f"File '{f.path}' belongs to folder "
                        f"'{f.folder}' which is not in the structure "
                        f"map."
                    ),
                    affected=f.path,
                    resolution_hint=(
                        f"Add folder '{f.folder}' to the structure "
                        f"map or move '{f.name}' to a valid folder."
                    ),
                ))

        return findings

    @staticmethod
    def _check_all_files_have_component(
        plan: FileGenerationPlan,
    ) -> List[PlanFinding]:
        """Check that every file has a source component.

        Files without a source component are flagged as warnings
        (they may be legitimate project-level files, but the
        validator notes them for review).
        """
        findings: List[PlanFinding] = []
        for f in plan.files:
            if not f.source_component:
                findings.append(PlanFinding(
                    severity=SEVERITY_WARNING,
                    code="file_without_component",
                    message=(
                        f"File '{f.path}' has no source component. "
                        f"It may be a project-level file, but this "
                        f"should be confirmed."
                    ),
                    affected=f.path,
                    resolution_hint=(
                        f"Link '{f.name}' to a component or confirm "
                        f"it is a standalone project file."
                    ),
                ))
        return findings

    @staticmethod
    def _check_all_relationships_valid(
        plan: FileGenerationPlan,
    ) -> List[PlanFinding]:
        """Check that all relationship sources and targets exist."""
        findings: List[PlanFinding] = []

        all_paths: Set[str] = {f.path for f in plan.files}

        for rel in plan.relationships:
            if rel.source not in all_paths:
                findings.append(PlanFinding(
                    severity=SEVERITY_ERROR,
                    code="invalid_relationship_source",
                    message=(
                        f"Relationship source '{rel.source}' does "
                        f"not exist in the plan."
                    ),
                    affected=rel.source,
                    resolution_hint=(
                        f"Remove the relationship or add a file at "
                        f"'{rel.source}'."
                    ),
                ))
            if rel.target not in all_paths:
                findings.append(PlanFinding(
                    severity=SEVERITY_ERROR,
                    code="invalid_relationship_target",
                    message=(
                        f"Relationship target '{rel.target}' does "
                        f"not exist in the plan."
                    ),
                    affected=rel.target,
                    resolution_hint=(
                        f"Remove the relationship or add a file at "
                        f"'{rel.target}'."
                    ),
                ))

        return findings

    @staticmethod
    def _check_generation_order_valid(
        plan: FileGenerationPlan,
    ) -> List[PlanFinding]:
        """Check that the generation order is valid.

        The generation order must:
        * contain every file exactly once,
        * be in topologically valid order (no file appears before a
          file it depends on).
        """
        findings: List[PlanFinding] = []

        all_paths: Set[str] = {f.path for f in plan.files}
        order_paths: List[str] = [o.file_path for o in plan.generation_order]

        # Check that every file is in the order.
        for path in all_paths:
            if path not in order_paths:
                findings.append(PlanFinding(
                    severity=SEVERITY_ERROR,
                    code="file_not_in_order",
                    message=(
                        f"File '{path}' is not in the generation "
                        f"order."
                    ),
                    affected=path,
                    resolution_hint=(
                        f"Add '{path}' to the generation order."
                    ),
                ))

        # Check for duplicates in the order.
        seen: Set[str] = set()
        for path in order_paths:
            if path in seen:
                findings.append(PlanFinding(
                    severity=SEVERITY_ERROR,
                    code="duplicate_in_order",
                    message=(
                        f"File '{path}' appears more than once in "
                        f"the generation order."
                    ),
                    affected=path,
                    resolution_hint=(
                        f"Remove the duplicate entry for '{path}'."
                    ),
                ))
            seen.add(path)

        # Check topological validity — a file must not appear before
        # any file it depends on.
        position_by_path: Dict[str, int] = {
            o.file_path: o.position for o in plan.generation_order
        }

        for f in plan.files:
            my_pos = position_by_path.get(f.path, -1)
            if my_pos < 0:
                continue  # already flagged as not in order

            for dep in f.depends_on:
                dep_pos = position_by_path.get(dep, -1)
                if dep_pos < 0:
                    continue  # dangling — already flagged
                if dep_pos > my_pos:
                    findings.append(PlanFinding(
                        severity=SEVERITY_ERROR,
                        code="invalid_generation_order",
                        message=(
                            f"File '{f.path}' (position {my_pos}) "
                            f"appears before its dependency "
                            f"'{dep}' (position {dep_pos})."
                        ),
                        affected=f.path,
                        resolution_hint=(
                            f"Move '{dep}' before '{f.path}' in "
                            f"the generation order."
                        ),
                    ))

        return findings


__all__ = ["PlanValidator"]
