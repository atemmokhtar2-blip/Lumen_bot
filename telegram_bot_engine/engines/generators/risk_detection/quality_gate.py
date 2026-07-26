"""
QualityGate — Specification 018

Ensures the Risk Analysis Report is complete and that no
critical risks block the generation pipeline.

The quality gate validates the Risk Analysis Report against four
quality rules:

    1. **No critical risks** — there are no critical-severity
       risks.  If a critical risk exists, the gate blocks
       the generation pipeline.
    2. **All dimensions analysed** — all seven risk dimensions
       have been analysed.
    3. **Risks have recommendations** — every detected risk has
       a corresponding recommendation.
    4. **Sufficient confidence** — the analysis confidence is
       at or above the medium threshold.

If the critical-risk rule fails, the gate blocks generation by
setting the verdict to NOT_READY.
"""

from __future__ import annotations

import logging
from typing import List, Tuple

from .report_data import (
    RiskAnalysisReport,
    RiskFinding,
    SEVERITY_CRITICAL,
    SEVERITY_HIGH,
    SEVERITY_MEDIUM,
    SEVERITY_LOW,
    RULE_NO_CRITICAL_RISKS,
    RULE_ALL_DIMENSIONS_ANALYSED,
    RULE_RISKS_HAVE_RECOMMENDATIONS,
    RULE_SUFFICIENT_CONFIDENCE,
    ALL_QUALITY_RULES,
    ALL_DIMENSIONS,
    CONFIDENCE_MEDIUM_THRESHOLD,
)

_log = logging.getLogger("engine.risk_detection.quality_gate")


class QualityGate:
    """Validates the Risk Analysis Report against quality rules.

    The quality gate checks:
    * No critical risks: there are no critical-severity risks.
    * All dimensions analysed: all seven dimensions are present.
    * Risks have recommendations: every risk has a recommendation.
    * Sufficient confidence: the confidence is above the medium
      threshold.

    If the no-critical-risks rule fails, the gate blocks
    generation by returning passed=False.
    """

    def __init__(self) -> None:
        self._findings: List[RiskFinding] = []

    def validate(
        self,
        report: RiskAnalysisReport,
    ) -> Tuple[List[RiskFinding], bool]:
        """Validate the Risk Analysis Report.

        Args:
            report: The Risk Analysis Report to validate.

        Returns:
            A tuple of (findings, passed) where ``passed`` is
            True if the report passes all quality rules.
        """
        self._findings = []
        all_passed = True

        # Check if the report is empty.
        if report.is_empty:
            self._findings.append(RiskFinding(
                severity=SEVERITY_CRITICAL,
                code="empty_report",
                message=(
                    "The Risk Analysis Report is empty. "
                    "No risk analysis has been performed."
                ),
                affected="report",
                resolution_hint=(
                    "Ensure the Risk Detection Engine has "
                    "completed its analysis with available "
                    "data sources."
                ),
                category="quality",
            ))
            return self._findings, False

        # Validate each quality rule.
        for rule in ALL_QUALITY_RULES:
            rule_passed = self._validate_rule(rule, report)
            if not rule_passed:
                all_passed = False

        return self._findings, all_passed

    @property
    def findings(self) -> List[RiskFinding]:
        """Return all findings produced during validation."""
        return self._findings

    # ----------------------------------------------------------------- #
    # Private helpers
    # ----------------------------------------------------------------- #

    def _validate_rule(
        self,
        rule: str,
        report: RiskAnalysisReport,
    ) -> bool:
        """Validate a single quality rule.

        Args:
            rule: The quality rule name.
            report: The Risk Analysis Report.

        Returns:
            True if the rule passes.
        """
        if rule == RULE_NO_CRITICAL_RISKS:
            return self._validate_no_critical_risks(report)
        elif rule == RULE_ALL_DIMENSIONS_ANALYSED:
            return self._validate_all_dimensions(report)
        elif rule == RULE_RISKS_HAVE_RECOMMENDATIONS:
            return self._validate_recommendations(report)
        elif rule == RULE_SUFFICIENT_CONFIDENCE:
            return self._validate_confidence(report)
        return True

    def _validate_no_critical_risks(
        self, report: RiskAnalysisReport
    ) -> bool:
        """Validate the no-critical-risks rule.

        If there are critical-severity risks, the gate blocks
        generation.

        Args:
            report: The Risk Analysis Report.

        Returns:
            True if there are no critical risks.
        """
        critical = report.critical_risks()
        if critical:
            self._findings.append(RiskFinding(
                severity=SEVERITY_CRITICAL,
                code="critical_risks_present",
                message=(
                    f"{len(critical)} critical-severity "
                    f"risk(s) detected. The generation pipeline "
                    f"is BLOCKED until these risks are addressed."
                ),
                affected="risks",
                resolution_hint=(
                    "Address all critical risks before "
                    "proceeding to the generation phase. "
                    "Each critical risk has a suggested fix."
                ),
                category="quality",
            ))
            return False
        return True

    def _validate_all_dimensions(
        self, report: RiskAnalysisReport
    ) -> bool:
        """Validate the all-dimensions-analysed rule.

        Checks that all seven risk dimensions have been analysed.

        Args:
            report: The Risk Analysis Report.

        Returns:
            True if all dimensions are present.
        """
        analysed = set(report.dimension_names())
        missing = [
            dim for dim in ALL_DIMENSIONS if dim not in analysed
        ]

        if missing:
            self._findings.append(RiskFinding(
                severity=SEVERITY_HIGH,
                code="missing_dimensions",
                message=(
                    f"{len(missing)} of {len(ALL_DIMENSIONS)} "
                    f"risk dimensions were not analysed: "
                    f"{', '.join(missing)}."
                ),
                affected="dimensions",
                resolution_hint=(
                    "Ensure all seven risk analyzers are "
                    "executed with available data sources."
                ),
                category="quality",
            ))
            return False
        return True

    def _validate_recommendations(
        self, report: RiskAnalysisReport
    ) -> bool:
        """Validate the risks-have-recommendations rule.

        Checks that every detected risk has a corresponding
        recommendation.

        Args:
            report: The Risk Analysis Report.

        Returns:
            True if all risks have recommendations.
        """
        if not report.risks:
            return True

        # Build a set of risk IDs covered by recommendations.
        covered: set = set()
        for rec in report.recommendations:
            covered.update(rec.related_risks)

        # Find risks without recommendations.
        uncovered = [
            r for r in report.risks
            if r.risk_id not in covered
        ]

        if uncovered:
            self._findings.append(RiskFinding(
                severity=SEVERITY_MEDIUM,
                code="risks_without_recommendations",
                message=(
                    f"{len(uncovered)} of {report.risk_count} "
                    f"risk(s) have no corresponding "
                    f"recommendation."
                ),
                affected="recommendations",
                resolution_hint=(
                    "Ensure the report builder generates a "
                    "recommendation for every detected risk."
                ),
                category="quality",
            ))
            return False
        return True

    def _validate_confidence(
        self, report: RiskAnalysisReport
    ) -> bool:
        """Validate the sufficient-confidence rule.

        Checks that the analysis confidence is at or above
        the medium threshold.

        Args:
            report: The Risk Analysis Report.

        Returns:
            True if the confidence is sufficient.
        """
        if report.confidence < CONFIDENCE_MEDIUM_THRESHOLD:
            self._findings.append(RiskFinding(
                severity=SEVERITY_MEDIUM,
                code="low_confidence",
                message=(
                    f"Overall confidence ({report.confidence:.2f}) "
                    f"is below the medium threshold "
                    f"({CONFIDENCE_MEDIUM_THRESHOLD}). The risk "
                    f"analysis may be incomplete."
                ),
                affected="confidence",
                resolution_hint=(
                    "Provide more data sources to increase "
                    "confidence in the risk analysis."
                ),
                category="quality",
            ))
            return False
        return True


__all__ = ["QualityGate"]
