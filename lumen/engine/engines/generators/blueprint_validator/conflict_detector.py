"""
Conflict Detection (Specification 005).

The :class:`ConflictDetector` inspects the :class:`ProjectBlueprint` for
contradictions that would make the project impossible or incorrect to
build.  It is a pure, stateless helper invoked by the
:class:`BlueprintValidatorEngine`.

Detected conflicts
------------------
* **Incompatible database** — a database is declared but the chosen
  database is not one of the supported backends.
* **Unsupported framework** — the declared Telegram framework is not in
  the supported set.
* **Feature depends on missing feature** — a feature unit declares a
  dependency on another feature that does not exist in the blueprint.
* **Phase depends on uncreated phase** — a phase references another
  phase that does not exist in the execution plan.

The detector does **not** fix conflicts — it only reports them.  The
validator engine decides whether the report causes a rejection.
"""

from __future__ import annotations

from typing import List

from .validation_report import (
    SEVERITY_ERROR,
    SEVERITY_WARNING,
    ConflictFinding,
)
from ..project_planner.blueprint import ProjectBlueprint
from ..project_planner.feature_unit import FeatureUnit
from ..project_planner.dependency_graph import DependencyGraph
from ..project_planner.execution_plan import ExecutionPlan


# Supported database backends.  Adding a new database requires updating
# this set and the planning engine's library mapping.
SUPPORTED_DATABASES = frozenset({
    "sqlite", "postgres", "postgresql", "mysql", "",
})

# Supported Telegram bot frameworks.
SUPPORTED_FRAMEWORKS = frozenset({
    "python-telegram-bot", "aiogram", "telebot", "pyrogram",
})


class ConflictDetector:
    """Detects contradictions in a :class:`ProjectBlueprint`."""

    def detect(self, blueprint: ProjectBlueprint) -> List[ConflictFinding]:
        """Run all conflict checks and return the combined list."""
        conflicts: List[ConflictFinding] = []
        conflicts.extend(self._detect_incompatible_database(blueprint))
        conflicts.extend(self._detect_unsupported_framework(blueprint))
        conflicts.extend(
            self._detect_feature_depends_on_missing(blueprint))
        conflicts.extend(
            self._detect_phase_depends_on_missing(blueprint))
        conflicts.extend(self._detect_component_conflicts(blueprint))
        return conflicts

    # -- individual checks -------------------------------------------------#

    def _detect_incompatible_database(
        self, blueprint: ProjectBlueprint) -> List[ConflictFinding]:
        """Check that the declared database is supported."""
        conflicts: List[ConflictFinding] = []
        db = (blueprint.identity.database or "").lower().strip()
        if db and db not in SUPPORTED_DATABASES:
            conflicts.append(ConflictFinding(
                kind="incompatible_database",
                description=(
                    f"Database '{db}' is not in the list of supported "
                    f"backends {sorted(SUPPORTED_DATABASES - {''})}."
                ),
                severity=SEVERITY_ERROR,
                affected=db,
                resolution_hint=(
                    "Choose a supported database (sqlite, postgres, or "
                    "mysql) or remove the database requirement."
                ),
            ))
        # A feature requires a database but no database is declared.
        if not db:
            needs_db = any(
                f.requires_database for f in blueprint.features
            )
            if needs_db:
                conflicts.append(ConflictFinding(
                    kind="incompatible_database",
                    description=(
                        "One or more features require a database but no "
                        "database backend was declared in the project "
                        "identity."
                    ),
                    severity=SEVERITY_ERROR,
                    affected=", ".join(
                        f.name for f in blueprint.features
                        if f.requires_database),
                    resolution_hint=(
                        "Declare a database in the project identity or "
                        "remove the database requirement from the features."
                    ),
                ))
        return conflicts

    def _detect_unsupported_framework(
        self, blueprint: ProjectBlueprint) -> List[ConflictFinding]:
        """Check that the declared framework is supported."""
        conflicts: List[ConflictFinding] = []
        framework = (blueprint.identity.framework or "").lower().strip()
        if framework and framework not in SUPPORTED_FRAMEWORKS:
            conflicts.append(ConflictFinding(
                kind="unsupported_framework",
                description=(
                    f"Framework '{framework}' is not in the list of "
                    f"supported frameworks {sorted(SUPPORTED_FRAMEWORKS)}."
                ),
                severity=SEVERITY_ERROR,
                affected=framework,
                resolution_hint=(
                    "Choose a supported Telegram bot framework."
                ),
            ))
        return conflicts

    def _detect_feature_depends_on_missing(
        self, blueprint: ProjectBlueprint) -> List[ConflictFinding]:
        """Detect features that depend on non-existent features."""
        conflicts: List[ConflictFinding] = []
        feature_names = {f.name for f in blueprint.features}
        for unit in blueprint.features:
            for dep in unit.depends_on_features:
                if dep not in feature_names:
                    conflicts.append(ConflictFinding(
                        kind="feature_depends_on_missing",
                        description=(
                            f"Feature '{unit.name}' depends on feature "
                            f"'{dep}' which does not exist in the "
                            f"blueprint."
                        ),
                        severity=SEVERITY_ERROR,
                        affected=unit.name,
                        resolution_hint=(
                            f"Add the missing feature '{dep}' or remove "
                            f"the dependency from '{unit.name}'."
                        ),
                    ))
        return conflicts

    def _detect_phase_depends_on_missing(
        self, blueprint: ProjectBlueprint) -> List[ConflictFinding]:
        """Detect phases that reference non-existent phases.

        This check looks for parallel-design entries that reference
        phase names not present in the execution plan.
        """
        conflicts: List[ConflictFinding] = []
        plan = blueprint.execution_plan
        plan_phase_names = {p.name for p in plan.phases}
        parallel_design = plan.parallel_design or {}
        for key in ("parallel_phases", "sequential_phases"):
            phases_ref = parallel_design.get(key, [])
            for ref in phases_ref:
                if ref not in plan_phase_names:
                    conflicts.append(ConflictFinding(
                        kind="phase_depends_on_missing",
                        description=(
                            f"Parallel design key '{key}' references "
                            f"phase '{ref}' which does not exist in the "
                            f"execution plan."
                        ),
                        severity=SEVERITY_WARNING,
                        affected=ref,
                        resolution_hint=(
                            "Update the parallel design to reference only "
                            "existing phases."
                        ),
                    ))
        return conflicts

    def _detect_component_conflicts(
        self, blueprint: ProjectBlueprint) -> List[ConflictFinding]:
        """Detect components that depend on non-existent components."""
        conflicts: List[ConflictFinding] = []
        component_names = {c.name for c in blueprint.components}
        for comp in blueprint.components:
            for dep in comp.dependencies:
                if dep not in component_names:
                    conflicts.append(ConflictFinding(
                        kind="feature_depends_on_missing",
                        description=(
                            f"Component '{comp.name}' depends on "
                            f"component '{dep}' which does not exist in "
                            f"the blueprint."
                        ),
                        severity=SEVERITY_ERROR,
                        affected=comp.name,
                        resolution_hint=(
                            f"Add the missing component '{dep}' or remove "
                            f"the dependency from '{comp.name}'."
                        ),
                    ))
        # Relationship endpoints that reference unknown components.
        for rel in blueprint.relationships:
            if rel.source not in component_names:
                conflicts.append(ConflictFinding(
                    kind="feature_depends_on_missing",
                    description=(
                        f"Relationship source '{rel.source}' is not a "
                        f"known component."
                    ),
                    severity=SEVERITY_ERROR,
                    affected=rel.source,
                    resolution_hint="Remove the dangling relationship.",
                ))
            if rel.target not in component_names:
                conflicts.append(ConflictFinding(
                    kind="feature_depends_on_missing",
                    description=(
                        f"Relationship target '{rel.target}' is not a "
                        f"known component."
                    ),
                    severity=SEVERITY_ERROR,
                    affected=rel.target,
                    resolution_hint="Remove the dangling relationship.",
                ))
        return conflicts


__all__ = [
    "ConflictDetector",
    "SUPPORTED_DATABASES",
    "SUPPORTED_FRAMEWORKS",
]
