"""
Quality gate \u2014 blocks requirements not converted to the canonical
model.

The :class:`QualityGate` is the component that validates the quality
of the Normalization Report.  It acts as a "gate" that blocks
requirements that have not been converted to the canonical model
from proceeding to downstream engines.

The quality gate checks:

1. **No requirements lost** \u2014 the number of active requirements
   must be at least as many as the original requirements (minus
   merged duplicates).
2. **All requirements linked** \u2014 every active requirement must
   have a feature or component link.
3. **No remaining duplicates** \u2014 the deduplication must have
   removed all duplicates.
4. **No unresolved conflicts** \u2014 there must be no unresolved
   conflicts.
5. **Confidence level** \u2014 the overall confidence must be at or
   above the medium threshold.
6. **No empty report** \u2014 the report must have at least one
   requirement.

For each check that fails, the quality gate adds a
:class:`NormalizationFinding` to the report.  If any error-level
finding is added, the gate blocks the request.

The quality gate does **not** fix the issues \u2014 it only detects
them and records findings.  The caller is responsible for resolving
the issues.

This module is a pure processing component: it has no side effects
and does not modify the generation context.
"""

from __future__ import annotations

from typing import List, Tuple

from .report_data import (
    CONFIDENCE_MEDIUM_THRESHOLD,
    NormalizationFinding,
    NormalizationReport,
    SEVERITY_ERROR,
    SEVERITY_WARNING,
    STATUS_ACTIVE,
)


class QualityGate:
    """Validates the quality of the Normalization Report.

    The quality gate checks the report and adds findings for any
    quality issues detected.  If any error-level finding is added,
    the gate blocks the request.

    The quality gate does **not** fix the issues \u2014 it only
    detects them.  The caller is responsible for resolving the
    issues.
    """

    def __init__(self) -> None:
        pass

    def validate(
        self,
        report: NormalizationReport,
        original_requirement_count: int = 0,
    ) -> Tuple[List[NormalizationFinding], bool]:
        """Validate the report and return the findings and the
        pass/fail status.

        Parameters:
            report: The Normalization Report to validate.
            original_requirement_count: The number of original
                requirements before normalization (for the
                lost-requirement check).

        Returns:
            A tuple ``(findings, passed)`` where ``findings`` is a
            list of :class:`NormalizationFinding` objects added by
            the quality gate, and ``passed`` is ``True`` if the
            report passed all quality checks.
        """
        findings: List[NormalizationFinding] = []

        # Check 1: No empty report.
        if report.is_empty:
            findings.append(NormalizationFinding(
                severity=SEVERITY_ERROR,
                code="empty_report",
                message=(
                    "The Normalization Report has no requirements. "
                    "There is nothing to normalize."
                ),
                affected="requirements",
                resolution_hint=(
                    "Provide requirements for the engine to "
                    "normalize."
                ),
                category="quality",
            ))

        # Check 2: All active requirements must be linked.
        unlinked = [
            req for req in report.requirements
            if req.status == STATUS_ACTIVE
            and not req.feature and not req.component
        ]
        if unlinked and report.requirement_count > 0:
            findings.append(NormalizationFinding(
                severity=SEVERITY_ERROR,
                code="unlinked_requirements",
                message=(
                    f"{len(unlinked)} active requirement(s) have "
                    f"no feature or component link. Every "
                    f"requirement must be linked to a feature or "
                    f"component."
                ),
                affected=",".join(req.id for req in unlinked),
                resolution_hint=(
                    "Provide project context with feature and "
                    "component names, or ensure the requirement "
                    "names match existing features or components."
                ),
                category="linking",
            ))

        # Check 3: No remaining duplicates.
        if report.has_duplicates:
            findings.append(NormalizationFinding(
                severity=SEVERITY_WARNING,
                code="duplicates_found",
                message=(
                    f"{report.duplicate_count} duplicate(s) were "
                    f"found and removed during normalization."
                ),
                affected="duplicates",
                resolution_hint=(
                    "Duplicates were merged. No action required, "
                    "but the user may want to review the merges."
                ),
                category="consistency",
            ))

        # Check 4: No unresolved conflicts.
        if report.has_unresolved_conflicts:
            findings.append(NormalizationFinding(
                severity=SEVERITY_ERROR,
                code="unresolved_conflicts",
                message=(
                    f"There are {report.conflict_count} "
                    f"conflict(s), all unresolved. The engine "
                    f"cannot proceed until these conflicts are "
                    f"resolved."
                ),
                affected="conflicts",
                resolution_hint=(
                    "Resolve the conflicts by choosing one value "
                    "or clarifying the requirements."
                ),
                category="consistency",
            ))

        # Check 5: Confidence level.
        if report.confidence < CONFIDENCE_MEDIUM_THRESHOLD:
            findings.append(NormalizationFinding(
                severity=SEVERITY_WARNING,
                code="low_confidence",
                message=(
                    f"The confidence score ({report.confidence:.1%}) "
                    f"is below the medium threshold "
                    f"({CONFIDENCE_MEDIUM_THRESHOLD:.0%}). The "
                    f"engine is not confident that the "
                    f"normalization is correct."
                ),
                affected="confidence",
                resolution_hint=(
                    "Provide more detail in the request, or "
                    "clarify ambiguous points to increase the "
                    "confidence."
                ),
                category="quality",
            ))

        # Check 6: No lost requirements.
        if original_requirement_count > 0:
            total = (
                report.requirement_count + report.duplicate_count
            )
            if total < original_requirement_count:
                findings.append(NormalizationFinding(
                    severity=SEVERITY_ERROR,
                    code="lost_requirements",
                    message=(
                        f"{original_requirement_count - total} "
                        f"requirement(s) were lost during "
                        f"normalization. Original: "
                        f"{original_requirement_count}, after: "
                        f"{total}."
                    ),
                    affected="requirements",
                    resolution_hint=(
                        "Ensure all requirements are preserved "
                        "during normalization."
                    ),
                    category="consistency",
                ))

        # Add the findings to the report.
        for finding in findings:
            report.findings.append(finding)
            if finding.severity == SEVERITY_WARNING:
                report.warnings.append(finding.message)

        # Determine if the report passed.
        has_errors = any(
            f.severity == SEVERITY_ERROR for f in findings
        )
        passed = not has_errors

        return findings, passed


__all__ = ["QualityGate"]
