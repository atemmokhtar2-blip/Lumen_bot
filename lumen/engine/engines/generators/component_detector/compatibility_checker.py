"""
Compatibility Checker — verifies that components are compatible with
the project's language, framework, and libraries (Specification 007).

The :class:`CompatibilityChecker` is a stateless helper that the
:class:`ComponentDetectionEngine` calls during the *validation* phase.
It checks each :class:`DetectedComponent` to ensure it is compatible
with the project's technology stack as declared in the
:class:`ProjectBlueprint`'s :class:`ProjectIdentity`.

The checker performs these checks:

1. **Compatible flag.**  Every component should have
   ``compatible=True``.  If a component is not compatible, the checker
   records an error.
2. **Language compatibility.**  The component's building engine should
   produce code in the project's language (Python).  All detected
   components are checked against the blueprint's ``language`` field.
3. **Framework compatibility.**  The component's type should be valid
   within the project's Telegram bot framework.  All component types
   in the registry are valid for the supported framework.

The checker does **not** modify components — it only records findings.
"""

from __future__ import annotations

from typing import List

from ..project_planner.blueprint import ProjectBlueprint
from .registry import (
    ALL_COMPONENT_TYPES,
    DetectedComponent,
    DetectionFinding,
    SEVERITY_ERROR,
    SEVERITY_WARNING,
)


# Languages the engine supports.
_SUPPORTED_LANGUAGES = frozenset({"python"})


class CompatibilityChecker:
    """Stateless helper that checks component compatibility.

    The checker is called by the
    :class:`ComponentDetectionEngine` after the
    :class:`TypeDetector` has produced the list of components.
    """

    def check(
        self,
        components: List[DetectedComponent],
        blueprint: ProjectBlueprint,
    ) -> List[DetectionFinding]:
        """Check the compatibility of each component with the project.

        Parameters:
            components: The list of detected components.
            blueprint: The project blueprint (for language, framework,
                and libraries).

        Returns:
            A list of :class:`DetectionFinding` objects.
        """
        findings: List[DetectionFinding] = []

        language = blueprint.identity.language.lower()
        framework = blueprint.identity.framework.lower()

        # Check the language is supported.
        if language not in _SUPPORTED_LANGUAGES:
            findings.append(DetectionFinding(
                severity=SEVERITY_ERROR,
                code="unsupported_language",
                message=(
                    f"The project language '{language}' is not "
                    f"supported by the component detection engine. "
                    f"Supported languages: "
                    f"{', '.join(sorted(_SUPPORTED_LANGUAGES))}."
                ),
                affected="project",
                resolution_hint=(
                    f"Use a supported language or add support for "
                    f"'{language}'."
                ),
            ))

        for comp in components:
            # Check compatible flag.
            if not comp.compatible:
                findings.append(DetectionFinding(
                    severity=SEVERITY_ERROR,
                    code="incompatible_component",
                    message=(
                        f"Component '{comp.name}' is marked as not "
                        f"compatible with the project's technology "
                        f"stack (language='{language}', "
                        f"framework='{framework}')."
                    ),
                    affected=comp.name,
                    resolution_hint=(
                        f"Review '{comp.name}' for compatibility with "
                        f"the project's stack."
                    ),
                ))

            # Check component type is known.
            if comp.type not in ALL_COMPONENT_TYPES:
                findings.append(DetectionFinding(
                    severity=SEVERITY_ERROR,
                    code="unknown_component_type",
                    message=(
                        f"Component '{comp.name}' has unknown type "
                        f"'{comp.type}'.  Known types: "
                        f"{', '.join(ALL_COMPONENT_TYPES)}."
                    ),
                    affected=comp.name,
                    resolution_hint=(
                        f"Use a known component type for '{comp.name}'."
                    ),
                ))

            # Check building engine is non-empty.
            if not comp.building_engine:
                findings.append(DetectionFinding(
                    severity=SEVERITY_WARNING,
                    code="missing_building_engine",
                    message=(
                        f"Component '{comp.name}' has no building "
                        f"engine assigned."
                    ),
                    affected=comp.name,
                    resolution_hint=(
                        f"Assign a building engine to '{comp.name}'."
                    ),
                ))

        return findings


__all__ = ["CompatibilityChecker"]
