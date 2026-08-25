"""
Scalability Checker — verifies that components are extensible and
reusable (Specification 007).

The :class:`ScalabilityChecker` is a stateless helper that the
:class:`ComponentDetectionEngine` calls during the *validation* phase.
It checks each :class:`DetectedComponent` to ensure it is designed for
scalability — it can be extended or reused without requiring
restructuring.

The checker performs these checks:

1. **Scalable flag.**  Every component should have ``scalable=True``.
   If a component is not scalable, the checker records a warning.
2. **Reusable flag.**  Components that are inherently reusable
   (repositories, validators, builders, utilities, API clients) should
   have ``reusable=True``.  If a reusable-type component is marked
   non-reusable, the checker records a warning.
3. **Extensible design.**  Components that have no ``depended_by``
   entries and are not application/entry-point components may be
   unused or overly narrow — the checker records an info-level note.

The checker does **not** modify components — it only records findings.
"""

from __future__ import annotations

from typing import List

from .registry import (
    COMPONENT_TYPE_APPLICATION,
    COMPONENT_TYPE_API_CLIENT,
    COMPONENT_TYPE_CALLBACK_HANDLER,
    COMPONENT_TYPE_COMMAND,
    COMPONENT_TYPE_KEYBOARD_BUILDER,
    COMPONENT_TYPE_MESSAGE_BUILDER,
    COMPONENT_TYPE_REPOSITORY,
    COMPONENT_TYPE_SESSION,
    COMPONENT_TYPE_UTILITY,
    COMPONENT_TYPE_VALIDATOR,
    DetectedComponent,
    DetectionFinding,
    SEVERITY_INFO,
    SEVERITY_WARNING,
)

# Component types that are inherently reusable.
_REUSABLE_TYPES = frozenset({
    COMPONENT_TYPE_REPOSITORY,
    COMPONENT_TYPE_VALIDATOR,
    COMPONENT_TYPE_KEYBOARD_BUILDER,
    COMPONENT_TYPE_MESSAGE_BUILDER,
    COMPONENT_TYPE_UTILITY,
    COMPONENT_TYPE_API_CLIENT,
})

# Component types that are inherently non-reusable (project-specific).
_NON_REUSABLE_TYPES = frozenset({
    COMPONENT_TYPE_APPLICATION,
    COMPONENT_TYPE_COMMAND,
    COMPONENT_TYPE_CALLBACK_HANDLER,
    COMPONENT_TYPE_SESSION,
})


class ScalabilityChecker:
    """Stateless helper that checks component scalability and reusability.

    The checker is called by the
    :class:`ComponentDetectionEngine` after the
    :class:`DuplicateDetector` has produced the final list of
    components.
    """

    def check(
        self,
        components: List[DetectedComponent],
    ) -> List[DetectionFinding]:
        """Check the scalability and reusability of each component.

        Parameters:
            components: The list of detected components.

        Returns:
            A list of :class:`DetectionFinding` objects.
        """
        findings: List[DetectionFinding] = []

        for comp in components:
            # Check scalable flag.
            if not comp.scalable:
                findings.append(DetectionFinding(
                    severity=SEVERITY_WARNING,
                    code="not_scalable",
                    message=(
                        f"Component '{comp.name}' is marked as not "
                        f"scalable.  Components should be designed to "
                        f"allow extension without restructuring."
                    ),
                    affected=comp.name,
                    resolution_hint=(
                        f"Review '{comp.name}' to ensure it can be "
                        f"extended without breaking changes."
                    ),
                ))

            # Check reusable flag for reusable-type components.
            if comp.type in _REUSABLE_TYPES and not comp.reusable:
                findings.append(DetectionFinding(
                    severity=SEVERITY_WARNING,
                    code="reusable_type_not_reusable",
                    message=(
                        f"Component '{comp.name}' is of type "
                        f"'{comp.type}' which should be reusable, but "
                        f"it is marked as not reusable."
                    ),
                    affected=comp.name,
                    resolution_hint=(
                        f"Mark '{comp.name}' as reusable or review "
                        f"its design for generality."
                    ),
                ))

            # Check for potentially unused components (no dependents).
            if (
                not comp.depended_by
                and comp.type not in _NON_REUSABLE_TYPES
                and comp.type != COMPONENT_TYPE_APPLICATION
            ):
                findings.append(DetectionFinding(
                    severity=SEVERITY_INFO,
                    code="no_dependents",
                    message=(
                        f"Component '{comp.name}' has no components "
                        f"that depend on it.  Verify it is used by "
                        f"the project entry point or other components."
                    ),
                    affected=comp.name,
                    resolution_hint=(
                        f"Ensure '{comp.name}' is referenced by at "
                        f"least one other component or the entry point."
                    ),
                ))

        return findings


__all__ = ["ScalabilityChecker"]
