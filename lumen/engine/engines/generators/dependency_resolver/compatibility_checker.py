"""
Compatibility Checker — checks the compatibility of all dependencies
with the language, framework, operating system, and each other
(Specification 009).

The :class:`CompatibilityChecker` is a stateless helper that the
:class:`DependencyResolutionEngine` calls during the *compatibility*
phase.  It checks each :class:`DependencyEntry` against the project's
declared language, framework, and operating system, and checks that
the inter-dependency relationships are compatible.

The checker does **not** modify the dependencies — it only records
findings.

Data source
-----------
The checker reads **only**:

1. the list of :class:`DependencyEntry` objects,
2. the :class:`ProjectBlueprint` (for the declared language,
   framework, and OS), and
3. the :class:`DependencyRelationship` objects (for inter-library
   compatibility).

It does **not** read the user's request.
"""

from __future__ import annotations

from typing import List

from ..project_planner.blueprint import ProjectBlueprint
from .report_data import (
    DependencyEntry,
    DependencyRelationship,
    ResolutionFinding,
    SEVERITY_ERROR,
    SEVERITY_INFO,
    SEVERITY_WARNING,
)


# ---------------------------------------------------------------------------#
# Known language → supported frameworks
# ---------------------------------------------------------------------------#

_LANGUAGE_FRAMEWORKS: dict = {
    "python": [
        "python-telegram-bot",
        "aiogram",
        "pyrogram",
        "telethon",
        "flask",
        "fastapi",
        "django",
    ],
}

# The default OS compatibility for Python packages.
_DEFAULT_OS_COMPAT = ["linux", "windows", "macos"]


class CompatibilityChecker:
    """Stateless helper that checks dependency compatibility.

    The checker is called by the
    :class:`DependencyResolutionEngine` after the
    :class:`DependencyGraphBuilder` has wired the dependencies.  It
    checks language, framework, OS, and inter-library compatibility.
    """

    def check(
        self,
        dependencies: List[DependencyEntry],
        relationships: List[DependencyRelationship],
        blueprint: ProjectBlueprint,
    ) -> List[ResolutionFinding]:
        """Check the compatibility of all dependencies.

        Parameters:
            dependencies: The list of dependency entries.
            relationships: The list of dependency relationships.
            blueprint: The project blueprint (for language, framework).

        Returns:
            A list of :class:`ResolutionFinding` objects describing all
            compatibility issues found.
        """
        findings: List[ResolutionFinding] = []

        findings.extend(
            self._check_language_compatibility(dependencies, blueprint)
        )
        findings.extend(
            self._check_framework_compatibility(dependencies, blueprint)
        )
        findings.extend(
            self._check_os_compatibility(dependencies)
        )
        findings.extend(
            self._check_inter_library_compatibility(
                dependencies, relationships,
            )
        )
        findings.extend(
            self._check_version_compatibility(dependencies)
        )

        return findings

    # -----------------------------------------------------------------#
    # Compatibility checks
    # -----------------------------------------------------------------#

    @staticmethod
    def _check_language_compatibility(
        dependencies: List[DependencyEntry],
        blueprint: ProjectBlueprint,
    ) -> List[ResolutionFinding]:
        """Check that all dependencies are compatible with the project language."""
        findings: List[ResolutionFinding] = []
        project_language = blueprint.identity.language

        for dep in dependencies:
            # If the dependency has a language set, it must match the
            # project's language.
            if dep.language and dep.language != project_language:
                findings.append(ResolutionFinding(
                    severity=SEVERITY_ERROR,
                    code="language_incompatible",
                    message=(
                        f"Dependency '{dep.name}' is for language "
                        f"'{dep.language}' but the project uses "
                        f"'{project_language}'."
                    ),
                    affected=dep.name,
                    resolution_hint=(
                        f"Replace '{dep.name}' with a "
                        f"'{project_language}'-compatible alternative."
                    ),
                    category="compatibility",
                ))

        return findings

    @staticmethod
    def _check_framework_compatibility(
        dependencies: List[DependencyEntry],
        blueprint: ProjectBlueprint,
    ) -> List[ResolutionFinding]:
        """Check that the framework is compatible with the language."""
        findings: List[ResolutionFinding] = []
        project_language = blueprint.identity.language
        project_framework = blueprint.identity.framework

        if project_framework:
            supported = _LANGUAGE_FRAMEWORKS.get(project_language, [])
            if supported and project_framework not in supported:
                findings.append(ResolutionFinding(
                    severity=SEVERITY_ERROR,
                    code="framework_incompatible",
                    message=(
                        f"Framework '{project_framework}' is not "
                        f"known to be compatible with language "
                        f"'{project_language}'."
                    ),
                    affected=project_framework,
                    resolution_hint=(
                        f"Use a {project_language}-compatible "
                        f"framework (e.g. "
                        f"{', '.join(supported[:3])})."
                    ),
                    category="compatibility",
                ))

        # Check that framework-typed dependencies match the project
        # framework.
        for dep in dependencies:
            if dep.type == "framework" and dep.framework:
                if dep.framework != project_framework:
                    findings.append(ResolutionFinding(
                        severity=SEVERITY_WARNING,
                        code="framework_mismatch",
                        message=(
                            f"Framework dependency '{dep.name}' "
                            f"declares framework '{dep.framework}' "
                            f"but the project uses "
                            f"'{project_framework}'."
                        ),
                        affected=dep.name,
                        resolution_hint=(
                            f"Confirm that '{dep.name}' is compatible "
                            f"with '{project_framework}'."
                        ),
                        category="compatibility",
                    ))

        return findings

    @staticmethod
    def _check_os_compatibility(
        dependencies: List[DependencyEntry],
    ) -> List[ResolutionFinding]:
        """Check that all dependencies declare OS compatibility."""
        findings: List[ResolutionFinding] = []

        for dep in dependencies:
            if not dep.os_compatibility:
                findings.append(ResolutionFinding(
                    severity=SEVERITY_WARNING,
                    code="os_compatibility_unknown",
                    message=(
                        f"Dependency '{dep.name}' has no OS "
                        f"compatibility information."
                    ),
                    affected=dep.name,
                    resolution_hint=(
                        f"Verify that '{dep.name}' is compatible "
                        f"with the target operating system."
                    ),
                    category="compatibility",
                ))

        return findings

    @staticmethod
    def _check_inter_library_compatibility(
        dependencies: List[DependencyEntry],
        relationships: List[DependencyRelationship],
    ) -> List[ResolutionFinding]:
        """Check that inter-library relationships are compatible.

        This checks that every dependency referenced in a relationship
        exists in the dependency list, and that no dependency has a
        relationship with itself.
        """
        findings: List[ResolutionFinding] = []
        all_names = {d.name for d in dependencies}

        for rel in relationships:
            if rel.source not in all_names:
                findings.append(ResolutionFinding(
                    severity=SEVERITY_ERROR,
                    code="broken_relationship_source",
                    message=(
                        f"Relationship source '{rel.source}' does "
                        f"not exist in the dependency list."
                    ),
                    affected=rel.source,
                    resolution_hint=(
                        f"Add '{rel.source}' to the dependency list "
                        f"or remove the relationship."
                    ),
                    category="compatibility",
                ))
            if rel.target not in all_names:
                findings.append(ResolutionFinding(
                    severity=SEVERITY_ERROR,
                    code="broken_relationship_target",
                    message=(
                        f"Relationship target '{rel.target}' does "
                        f"not exist in the dependency list."
                    ),
                    affected=rel.target,
                    resolution_hint=(
                        f"Add '{rel.target}' to the dependency list "
                        f"or remove the relationship."
                    ),
                    category="compatibility",
                ))
            if rel.source == rel.target:
                findings.append(ResolutionFinding(
                    severity=SEVERITY_ERROR,
                    code="self_dependency",
                    message=(
                        f"Dependency '{rel.source}' has a "
                        f"relationship with itself."
                    ),
                    affected=rel.source,
                    resolution_hint=(
                        f"Remove the self-relationship on "
                        f"'{rel.source}'."
                    ),
                    category="compatibility",
                ))

        return findings

    @staticmethod
    def _check_version_compatibility(
        dependencies: List[DependencyEntry],
    ) -> List[ResolutionFinding]:
        """Check that version constraints are present and valid.

        This is a lightweight check — it flags dependencies without a
        version constraint as warnings, since unconstrained versions
        can lead to breakage.
        """
        findings: List[ResolutionFinding] = []

        for dep in dependencies:
            if not dep.version_constraint:
                findings.append(ResolutionFinding(
                    severity=SEVERITY_INFO,
                    code="no_version_constraint",
                    message=(
                        f"Dependency '{dep.name}' has no version "
                        f"constraint.  Unconstrained versions can "
                        f"lead to breakage."
                    ),
                    affected=dep.name,
                    resolution_hint=(
                        f"Add a version constraint for '{dep.name}'."
                    ),
                    category="compatibility",
                ))

        return findings


__all__ = ["CompatibilityChecker"]
