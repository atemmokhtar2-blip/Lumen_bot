"""
Responsibility Validator — enforces the Single Responsibility Principle
(Specification 007).

The :class:`ResponsibilityValidator` is a stateless helper that the
:class:`ComponentDetectionEngine` calls during the *validation* phase.
It checks each :class:`DetectedComponent` to ensure it carries a
single, clear responsibility.

The validator performs these checks:

1. **No empty responsibility.**  Every component must have a
   non-empty ``responsibility`` string.
2. **No empty purpose.**  Every component must have a non-empty
   ``purpose`` string.
3. **Single responsibility.**  The responsibility should describe one
   thing.  If the responsibility is empty or too vague (e.g. "handles
   everything"), the validator records a warning.

The validator does **not** split components or modify the list — it
only records findings.  The engine uses the findings to decide whether
the registry is valid or to report warnings to the user.
"""

from __future__ import annotations

from typing import List

from .registry import (
    DetectedComponent,
    DetectionFinding,
    SEVERITY_ERROR,
    SEVERITY_WARNING,
)


# Keywords that indicate a component is trying to do too much.
_OVERLOADED_KEYWORDS = (
    "and", "also", "plus", "as well as", "everything", "all-in-one",
    "misc", "miscellaneous", "various",
)


class ResponsibilityValidator:
    """Stateless helper that validates the Single Responsibility Principle.

    The validator is called by the
    :class:`ComponentDetectionEngine` after the
    :class:`TypeDetector` and :class:`DuplicateDetector` have produced
    the final list of components.  It records findings for any
    component that violates the SRP.
    """

    def validate(
        self,
        components: List[DetectedComponent],
    ) -> List[DetectionFinding]:
        """Validate the responsibility of each component.

        Parameters:
            components: The list of detected components.

        Returns:
            A list of :class:`DetectionFinding` objects describing any
            SRP violations.
        """
        findings: List[DetectionFinding] = []

        for comp in components:
            # Check for empty responsibility.
            if not comp.responsibility or not comp.responsibility.strip():
                findings.append(DetectionFinding(
                    severity=SEVERITY_ERROR,
                    code="empty_responsibility",
                    message=(
                        f"Component '{comp.name}' has no responsibility "
                        f"defined.  Every component must have a single, "
                        f"clear responsibility (Single Responsibility "
                        f"Principle)."
                    ),
                    affected=comp.name,
                    resolution_hint=(
                        f"Define the single responsibility for "
                        f"'{comp.name}'."
                    ),
                ))
                continue

            # Check for empty purpose.
            if not comp.purpose or not comp.purpose.strip():
                findings.append(DetectionFinding(
                    severity=SEVERITY_WARNING,
                    code="empty_purpose",
                    message=(
                        f"Component '{comp.name}' has no purpose "
                        f"defined."
                    ),
                    affected=comp.name,
                    resolution_hint=(
                        f"Define the purpose for '{comp.name}'."
                    ),
                ))

            # Check for overloaded responsibility.
            resp_lower = comp.responsibility.lower()
            for keyword in _OVERLOADED_KEYWORDS:
                if keyword in resp_lower:
                    findings.append(DetectionFinding(
                        severity=SEVERITY_WARNING,
                        code="overloaded_responsibility",
                        message=(
                            f"Component '{comp.name}' may have "
                            f"multiple responsibilities (keyword "
                            f"'{keyword}' found in its responsibility "
                            f"description).  Consider splitting it into "
                            f"separate components."
                        ),
                        affected=comp.name,
                        resolution_hint=(
                            f"Split '{comp.name}' into separate "
                            f"components, each with a single "
                            f"responsibility."
                        ),
                    ))
                    break  # one warning per component is enough

        return findings


__all__ = ["ResponsibilityValidator"]
