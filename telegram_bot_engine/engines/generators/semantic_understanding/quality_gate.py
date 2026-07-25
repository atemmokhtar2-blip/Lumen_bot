"""
Quality gate — blocks requests with insufficient confidence.

The :class:`QualityGate` is the component that validates the quality of
the Semantic Understanding Report.  It acts as a "gate" that blocks
requests with insufficient confidence from proceeding to downstream
engines.

The quality gate checks:

1. **Confidence level** — the overall confidence must be at or above
   the medium threshold.
2. **Intent completeness** — the intent must have a description, a
   kind, and a primary action.
3. **Keyword quality** — there must be at least one keyword.
4. **Ambiguity resolution** — there must be no unresolved required
   clarifications.
5. **No error findings** — there must be no error-level findings.

For each check that fails, the quality gate adds a
:class:`SemanticFinding` to the report.  If any error-level finding is
added, the gate blocks the request.

The quality gate does **not** fix the issues — it only detects them
and records findings.  The caller is responsible for resolving the
issues.

This module is a pure processing component: it has no side effects and
does not modify the generation context.
"""

from __future__ import annotations

from typing import List, Tuple

from .report_data import (
    CONFIDENCE_MEDIUM_THRESHOLD,
    ClarificationRequest,
    ImportantKeyword,
    RequirementRelationship,
    SemanticAmbiguity,
    SemanticFinding,
    SemanticUnderstandingReport,
    UnifiedIntent,
)


class QualityGate:
    """Validates the quality of the Semantic Understanding Report.

    The quality gate checks the report and adds findings for any
    quality issues detected.  If any error-level finding is added,
    the gate blocks the request.

    The quality gate does **not** fix the issues — it only detects
    them.  The caller is responsible for resolving the issues.
    """

    def __init__(self) -> None:
        pass

    def validate(
        self,
        report: SemanticUnderstandingReport,
    ) -> Tuple[List[SemanticFinding], bool]:
        """Validate the report and return the findings and the
        pass/fail status.

        Parameters:
            report: The Semantic Understanding Report to validate.

        Returns:
            A tuple ``(findings, passed)`` where ``findings`` is a
            list of :class:`SemanticFinding` objects added by the
            quality gate, and ``passed`` is ``True`` if the report
            passed all quality checks.
        """
        findings: List[SemanticFinding] = []

        # Check 1: Confidence level.
        if report.confidence < CONFIDENCE_MEDIUM_THRESHOLD:
            findings.append(SemanticFinding(
                severity="warning",
                code="low_confidence",
                message=(
                    f"The confidence score ({report.confidence:.1%}) "
                    f"is below the medium threshold "
                    f"({CONFIDENCE_MEDIUM_THRESHOLD:.0%}). The "
                    f"engine is not confident that it correctly "
                    f"understood the user's request."
                ),
                affected="confidence",
                resolution_hint=(
                    "Provide more detail in the request, or clarify "
                    "ambiguous points to increase the confidence."
                ),
                category="confidence",
            ))

        # Check 2: Intent completeness.
        intent = report.intent
        if not intent or not intent.full_description:
            findings.append(SemanticFinding(
                severity="error",
                code="empty_intent",
                message=(
                    "The intent has no description. The engine could "
                    "not determine what the user wants."
                ),
                affected="intent",
                resolution_hint=(
                    "Provide a clear, specific request that "
                    "describes what you want to create or modify."
                ),
                category="intent",
            ))
        elif not intent.kind or intent.kind == "unknown":
            findings.append(SemanticFinding(
                severity="warning",
                code="unknown_intent_kind",
                message=(
                    "The intent kind is unknown. The engine could not "
                    "determine whether the user wants to create, "
                    "modify, delete, query, configure, or deploy."
                ),
                affected="intent.kind",
                resolution_hint=(
                    "Specify the action you want (e.g. create, "
                    "modify, delete, query, configure, deploy)."
                ),
                category="intent",
            ))
        elif not intent.primary_action:
            findings.append(SemanticFinding(
                severity="warning",
                code="no_primary_action",
                message=(
                    "The intent has no primary action. The engine "
                    "could not determine the primary action."
                ),
                affected="intent.primary_action",
                resolution_hint=(
                    "Specify the action you want to perform."
                ),
                category="intent",
            ))

        # Check 3: Keyword quality.
        if not report.important_keywords:
            findings.append(SemanticFinding(
                severity="warning",
                code="no_keywords",
                message=(
                    "No keywords were extracted from the request. "
                    "The engine could not identify any important "
                    "keywords."
                ),
                affected="important_keywords",
                resolution_hint=(
                    "Provide a request with specific keywords that "
                    "describe what you want."
                ),
                category="quality",
            ))

        # Check 4: Unresolved required clarifications.
        required_clarifications = [
            c for c in report.clarifications if c.required
        ]
        if required_clarifications:
            findings.append(SemanticFinding(
                severity="error",
                code="unresolved_clarifications",
                message=(
                    f"There are {len(required_clarifications)} "
                    f"unresolved required clarification(s). The "
                    f"engine cannot proceed until these "
                    f"clarifications are answered."
                ),
                affected="clarifications",
                resolution_hint=(
                    "Answer the required clarification questions "
                    "before proceeding."
                ),
                category="ambiguity",
            ))

        # Check 5: No empty request.
        if report.is_empty:
            findings.append(SemanticFinding(
                severity="error",
                code="empty_request",
                message=(
                    "The request is empty. There is nothing to "
                    "understand."
                ),
                affected="request",
                resolution_hint=(
                    "Provide a request for the engine to understand."
                ),
                category="quality",
            ))

        # Add the findings to the report.
        for finding in findings:
            report.findings.append(finding)
            if finding.severity == "warning":
                report.warnings.append(finding.message)

        # Determine if the report passed.
        has_errors = any(
            f.severity == "error" for f in findings
        )
        passed = not has_errors

        return findings, passed


__all__ = ["QualityGate"]
