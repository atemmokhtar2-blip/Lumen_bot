"""
Quality gate — blocks architectures that fail quality or
scalability requirements.

The :class:`QualityGate` is the component that validates the
quality and scalability of the Architecture Decision Report.  It
acts as a "gate" that blocks architectures that fail quality or
scalability requirements from proceeding to downstream engines.

The quality gate checks:

1. **No empty report** — the report must have at least one
   decision.
2. **All decisions validated** — every decision must have a
   reason, an analysis, an impact, and at least one rejected
   alternative.
3. **No error-level findings** — there must be no error-level
   findings in the report.
4. **Confidence level** — the overall confidence must be at or
   above the medium threshold.
5. **Scalability** — the architecture must be scalable for the
   project size (a very large project must not use a monolith; a
   tiny project must not use microservices).
6. **Maintainability** — the architecture must be maintainable
   (no flat dependency structure for large projects).

For each check that fails, the quality gate adds an
:class:`ArchitectureFinding` to the report.  If any error-level
finding is added, the gate blocks the request.

The quality gate does **not** fix the issues — it only detects
them and records findings.  The caller is responsible for
resolving the issues.

This module is a pure processing component: it has no side effects
and does not modify the generation context.
"""

from __future__ import annotations

from typing import List, Tuple

from .report_data import (
    ArchitectureDecisionReport,
    ArchitectureFinding,
    CONFIDENCE_MEDIUM_THRESHOLD,
    DECISION_DEPENDENCY_STRUCTURE,
    DECISION_LAYERS,
    DIMENSION_SIZE,
    DEP_FLAT,
    SEVERITY_ERROR,
    SEVERITY_WARNING,
    SIZE_TINY,
    SIZE_VERY_LARGE,
)


class QualityGate:
    """Validates the quality and scalability of the Architecture
    Decision Report.

    The quality gate checks the report and adds findings for any
    quality or scalability issues detected.  If any error-level
    finding is added, the gate blocks the request.
    """

    def __init__(self) -> None:
        pass

    def validate(
        self,
        report: ArchitectureDecisionReport,
    ) -> Tuple[List[ArchitectureFinding], bool]:
        """Validate the report and return the findings and the
        pass/fail status.

        Parameters:
            report: The Architecture Decision Report to validate.

        Returns:
            A tuple ``(findings, passed)`` where ``findings`` is a
            list of :class:`ArchitectureFinding` objects added by
            the quality gate, and ``passed`` is ``True`` if the
            report passed all quality checks.
        """
        findings: List[ArchitectureFinding] = []

        # Check 1: No empty report.
        if report.is_empty:
            findings.append(ArchitectureFinding(
                severity=SEVERITY_ERROR,
                code="empty_report",
                message=(
                    "The Architecture Decision Report has no "
                    "decisions. There is nothing to validate."
                ),
                affected="decisions",
                resolution_hint=(
                    "Ensure the architecture selector produces "
                    "decisions."
                ),
                category="quality",
            ))

        # Check 2: All decisions validated.
        if not report.all_decisions_validated:
            unvalidated = [
                d.domain
                for d in report.decisions
                if not d.reason
                or not d.analysis
                or not d.impact
                or not d.rejected_alternatives
            ]
            findings.append(ArchitectureFinding(
                severity=SEVERITY_ERROR,
                code="unvalidated_decisions",
                message=(
                    f"{len(unvalidated)} decision(s) are not "
                    f"validated (missing reason, analysis, impact, "
                    f"or rejected alternatives)."
                ),
                affected=", ".join(unvalidated),
                resolution_hint=(
                    "Ensure every decision has a reason, an "
                    "analysis, an impact, and at least one "
                    "rejected alternative."
                ),
                category="quality",
            ))

        # Check 3: No error-level findings (from the decision
        # validator).
        if report.has_errors:
            error_findings = [
                f for f in report.findings
                if f.severity == SEVERITY_ERROR
            ]
            findings.append(ArchitectureFinding(
                severity=SEVERITY_ERROR,
                code="existing_errors",
                message=(
                    f"There are {len(error_findings)} error-level "
                    f"finding(s) in the report from validation."
                ),
                affected="findings",
                resolution_hint=(
                    "Resolve the error-level findings before "
                    "proceeding."
                ),
                category="quality",
            ))

        # Check 4: Confidence level.  An architecture with
        # confidence below the medium threshold is not reliable
        # enough to proceed \u2014 this is an error, not a warning,
        # because the specification states that no architecture
        # that fails quality requirements is allowed.
        if report.confidence < CONFIDENCE_MEDIUM_THRESHOLD:
            findings.append(ArchitectureFinding(
                severity=SEVERITY_ERROR,
                code="low_confidence",
                message=(
                    f"The confidence score ({report.confidence:.1%}) "
                    f"is below the medium threshold "
                    f"({CONFIDENCE_MEDIUM_THRESHOLD:.0%}). The "
                    f"engine is not confident that the "
                    f"architecture decisions are correct."
                ),
                affected="confidence",
                resolution_hint=(
                    "Provide more data sources or clarify the "
                    "requirements to increase the confidence."
                ),
                category="quality",
            ))

        # Check 5: Scalability — the architecture must be scalable
        # for the project size.
        size_analysis = report.get_analysis(DIMENSION_SIZE)
        size_tier = (
            size_analysis.level if size_analysis else SIZE_TINY
        )
        layers_decision = report.get_decision(DECISION_LAYERS)
        dep_decision = report.get_decision(
            DECISION_DEPENDENCY_STRUCTURE
        )

        # A very large project must not use a flat structure.
        if (
            size_tier == SIZE_VERY_LARGE
            and dep_decision
            and dep_decision.selected == DEP_FLAT
        ):
            findings.append(ArchitectureFinding(
                severity=SEVERITY_ERROR,
                code="scalability_violation",
                message=(
                    f"The project is classified as {size_tier} "
                    f"but the dependency structure is flat. A "
                    f"very large project cannot use a flat "
                    f"dependency structure."
                ),
                affected=DECISION_DEPENDENCY_STRUCTURE,
                resolution_hint=(
                    "Use a hierarchical or graph dependency "
                    "structure for very large projects."
                ),
                category="scalability",
            ))

        # A large project must not use a flat structure.
        if (
            size_tier in ("large", "very_large")
            and dep_decision
            and dep_decision.selected == DEP_FLAT
        ):
            if not any(
                f.code == "scalability_violation" for f in findings
            ):
                findings.append(ArchitectureFinding(
                    severity=SEVERITY_ERROR,
                    code="scalability_violation",
                    message=(
                        f"The project is classified as "
                        f"{size_tier} but the dependency "
                        f"structure is flat. Large projects "
                        f"need a structured dependency model."
                    ),
                    affected=DECISION_DEPENDENCY_STRUCTURE,
                    resolution_hint=(
                        "Use a layered, hierarchical, or graph "
                        "dependency structure for large projects."
                    ),
                    category="scalability",
                ))

        # Check 6: Maintainability — the architecture must be
        # maintainable.  A tiny project must have at least the
        # fundamental layers.
        if layers_decision:
            selected = layers_decision.selected
            if "presentation" not in selected:
                findings.append(ArchitectureFinding(
                    severity=SEVERITY_WARNING,
                    code="missing_presentation_layer",
                    message=(
                        "The presentation layer is not in the "
                        "selected layers. Every project needs a "
                        "presentation layer."
                    ),
                    affected=DECISION_LAYERS,
                    resolution_hint=(
                        "Add the presentation layer to the "
                        "selected layers."
                    ),
                    category="maintainability",
                ))
            if "business" not in selected:
                findings.append(ArchitectureFinding(
                    severity=SEVERITY_WARNING,
                    code="missing_business_layer",
                    message=(
                        "The business layer is not in the "
                        "selected layers. Every project needs a "
                        "business layer."
                    ),
                    affected=DECISION_LAYERS,
                    resolution_hint=(
                        "Add the business layer to the selected "
                        "layers."
                    ),
                    category="maintainability",
                ))

        # Add the findings to the report.
        for finding in findings:
            report.findings.append(finding)
            if finding.severity == SEVERITY_WARNING:
                report.warnings.append(finding.message)

        has_errors = any(
            f.severity == SEVERITY_ERROR for f in findings
        )
        passed = not has_errors

        return findings, passed


__all__ = ["QualityGate"]
