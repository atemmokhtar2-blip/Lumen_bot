"""
QualityGate — Specification 017

Ensures the architecture can meet the project's performance,
scalability, and quality requirements.  Blocks generation if the
architecture is not capable.

The quality gate validates the Project Capability Report against
four quality rules:
    1. Performance — the architecture can handle the expected load.
    2. Scalability — the architecture can scale to the required
       user count.
    3. Quality — the dependency graph is healthy.
    4. Dependency Health — no circular, missing, or conflicting
       dependencies.
"""

from __future__ import annotations

import logging
from typing import List, Tuple

from .report_data import (
    ProjectCapabilityReport,
    CapabilityFinding,
    SEVERITY_ERROR,
    SEVERITY_WARNING,
    SEVERITY_INFO,
    RULE_PERFORMANCE,
    RULE_SCALABILITY,
    RULE_QUALITY,
    RULE_DEPENDENCY_HEALTH,
    ALL_QUALITY_RULES,
    LOAD_LIGHT,
    LOAD_MODERATE,
    LOAD_HEAVY,
    LOAD_PEAK,
    SCALE_THOUSANDS,
    SCALE_TENS_OF_THOUSANDS,
    SCALE_HUNDREDS_OF_THOUSANDS,
    SCALE_MILLIONS,
    CONFIDENCE_MEDIUM_THRESHOLD,
    VERDICT_CAPABLE,
    VERDICT_CAPABLE_WITH_RISKS,
    VERDICT_NOT_CAPABLE,
)

_log = logging.getLogger("engine.capability_analyzer.quality_gate")


# ---------------------------------------------------------------------------#
# Minimum thresholds
# ---------------------------------------------------------------------------#

MIN_PERFORMANCE_SCORE = 0.4   # Stress score must be at least 0.4
MIN_SCALABILITY_SCORE = 0.3   # Scalability score must be at least 0.3
MIN_QUALITY_SCORE = 0.5       # Dependency health score must be at least 0.5
MIN_DEPENDENCY_HEALTH = 0.5   # Dependency analysis score must be at least 0.5

# Minimum scalability tier required.
MIN_SCALABILITY_TIER = SCALE_THOUSANDS  # Must support at least thousands.

# Minimum load level required.
MIN_LOAD_LEVEL = LOAD_LIGHT  # Must sustain at least light load.

# Load level rank for comparison.
_LOAD_RANK = {
    LOAD_LIGHT: 1,
    LOAD_MODERATE: 2,
    LOAD_HEAVY: 3,
    LOAD_PEAK: 4,
}

# Scalability tier rank for comparison.
_TIER_RANK = {
    SCALE_THOUSANDS: 1,
    SCALE_TENS_OF_THOUSANDS: 2,
    SCALE_HUNDREDS_OF_THOUSANDS: 3,
    SCALE_MILLIONS: 4,
}


class QualityGate:
    """Validates the Project Capability Report against quality rules.

    The quality gate checks:
    * Performance: the architecture stress score meets the minimum.
    * Scalability: the architecture supports at least the minimum
      scalability tier.
    * Quality: the dependency graph is healthy.
    * Dependency Health: no critical dependency issues.

    If any rule fails with error severity, the gate blocks
    generation by setting the verdict to NOT_CAPABLE.
    """

    def __init__(self) -> None:
        self._findings: List[CapabilityFinding] = []

    def validate(
        self,
        report: ProjectCapabilityReport,
    ) -> Tuple[List[CapabilityFinding], bool]:
        """Validate the Project Capability Report.

        Args:
            report: The Project Capability Report to validate.

        Returns:
            A tuple of (findings, passed) where ``passed`` is True
            if the report passes all quality rules.
        """
        self._findings = []
        all_passed = True

        # Check if the report is empty.
        if report.is_empty:
            self._findings.append(CapabilityFinding(
                severity=SEVERITY_ERROR,
                code="empty_report",
                message=(
                    "The Project Capability Report is empty. "
                    "No analysis has been performed."
                ),
                affected="report",
                resolution_hint=(
                    "Ensure the Project Capability Analyzer "
                    "Engine has completed its analysis with "
                    "available data sources."
                ),
                category="quality",
            ))
            return self._findings, False

        # Validate each quality rule.
        for rule in ALL_QUALITY_RULES:
            rule_passed = self._validate_rule(rule, report)
            if not rule_passed:
                all_passed = False

        # Check all analyses were performed.
        if not report.all_analyses_performed:
            self._findings.append(CapabilityFinding(
                severity=SEVERITY_WARNING,
                code="incomplete_analyses",
                message=(
                    "Not all five analysis dimensions were "
                    "performed. The capability assessment may "
                    "be incomplete."
                ),
                affected="report",
                resolution_hint=(
                    "Ensure all five analyses (complexity, "
                    "resources, scalability, stress, "
                    "dependencies) are performed."
                ),
                category="quality",
            ))
            all_passed = False

        # Check confidence.
        if report.confidence < CONFIDENCE_MEDIUM_THRESHOLD:
            self._findings.append(CapabilityFinding(
                severity=SEVERITY_WARNING,
                code="low_confidence",
                message=(
                    f"Overall confidence ({report.confidence:.2f}) "
                    f"is below the medium threshold "
                    f"({CONFIDENCE_MEDIUM_THRESHOLD})."
                ),
                affected="report",
                resolution_hint=(
                    "Provide more data sources to increase "
                    "confidence in the capability assessment."
                ),
                category="quality",
            ))

        return self._findings, all_passed

    @property
    def findings(self) -> List[CapabilityFinding]:
        """Return all findings produced during validation."""
        return self._findings

    # ----------------------------------------------------------------- #
    # Private helpers
    # ----------------------------------------------------------------- #

    def _validate_rule(
        self,
        rule: str,
        report: ProjectCapabilityReport,
    ) -> bool:
        """Validate a single quality rule.

        Args:
            rule: The quality rule name.
            report: The Project Capability Report.

        Returns:
            True if the rule passes.
        """
        if rule == RULE_PERFORMANCE:
            return self._validate_performance(report)
        elif rule == RULE_SCALABILITY:
            return self._validate_scalability(report)
        elif rule == RULE_QUALITY:
            return self._validate_quality(report)
        elif rule == RULE_DEPENDENCY_HEALTH:
            return self._validate_dependency_health(report)
        return True

    def _validate_performance(
        self, report: ProjectCapabilityReport
    ) -> bool:
        """Validate the performance rule.

        Checks that the architecture stress score meets the minimum
        and the load level is at least the minimum.

        Args:
            report: The Project Capability Report.

        Returns:
            True if the performance rule passes.
        """
        passed = True

        stress_score = report.stress.score
        if stress_score < MIN_PERFORMANCE_SCORE:
            severity = (
                SEVERITY_ERROR
                if stress_score < MIN_PERFORMANCE_SCORE * 0.5
                else SEVERITY_WARNING
            )
            self._findings.append(CapabilityFinding(
                severity=severity,
                code="performance_score_low",
                message=(
                    f"Architecture stress score ({stress_score:.2f}) "
                    f"is below the minimum "
                    f"({MIN_PERFORMANCE_SCORE:.2f})."
                ),
                affected="architecture_stress",
                resolution_hint=(
                    "Address bottlenecks or select more "
                    "performant technologies."
                ),
                category="performance",
            ))
            if severity == SEVERITY_ERROR:
                passed = False

        # Check load level.
        load_level = report.stress.load_level
        if _LOAD_RANK.get(load_level, 0) < _LOAD_RANK.get(
            MIN_LOAD_LEVEL, 1
        ):
            self._findings.append(CapabilityFinding(
                severity=SEVERITY_WARNING,
                code="load_level_low",
                message=(
                    f"Architecture can only sustain "
                    f"'{load_level}' load, which is below "
                    f"the minimum '{MIN_LOAD_LEVEL}'."
                ),
                affected="architecture_stress",
                resolution_hint=(
                    "Improve the architecture to handle "
                    "higher load levels."
                ),
                category="performance",
            ))

        return passed

    def _validate_scalability(
        self, report: ProjectCapabilityReport
    ) -> bool:
        """Validate the scalability rule.

        Checks that the architecture supports at least the minimum
        scalability tier.

        Args:
            report: The Project Capability Report.

        Returns:
            True if the scalability rule passes.
        """
        passed = True

        scalability_score = report.scalability.score
        if scalability_score < MIN_SCALABILITY_SCORE:
            severity = (
                SEVERITY_ERROR
                if scalability_score < MIN_SCALABILITY_SCORE * 0.5
                else SEVERITY_WARNING
            )
            self._findings.append(CapabilityFinding(
                severity=severity,
                code="scalability_score_low",
                message=(
                    f"Scalability score ({scalability_score:.2f}) "
                    f"is below the minimum "
                    f"({MIN_SCALABILITY_SCORE:.2f})."
                ),
                affected="scalability",
                resolution_hint=(
                    "Consider a more scalable architecture "
                    "pattern or add scaling technologies."
                ),
                category="scalability",
            ))
            if severity == SEVERITY_ERROR:
                passed = False

        # Check max supported tier.
        max_tier = report.scalability.max_supported_tier
        if not max_tier:
            self._findings.append(CapabilityFinding(
                severity=SEVERITY_ERROR,
                code="no_scalability_tier",
                message=(
                    "The architecture does not support any "
                    "scalability tier."
                ),
                affected="scalability",
                resolution_hint=(
                    "Select a more scalable architecture "
                    "pattern or add caching and queuing "
                    "technologies."
                ),
                category="scalability",
            ))
            passed = False
        elif _TIER_RANK.get(max_tier, 0) < _TIER_RANK.get(
            MIN_SCALABILITY_TIER, 1
        ):
            self._findings.append(CapabilityFinding(
                severity=SEVERITY_WARNING,
                code="scalability_tier_low",
                message=(
                    f"Max supported tier '{max_tier}' is "
                    f"below the minimum '{MIN_SCALABILITY_TIER}'."
                ),
                affected="scalability",
                resolution_hint=(
                    "Improve the architecture to support "
                    "higher scalability tiers."
                ),
                category="scalability",
            ))

        return passed

    def _validate_quality(
        self, report: ProjectCapabilityReport
    ) -> bool:
        """Validate the quality rule.

        Checks that the overall quality of the analysis is
        sufficient — all analyses were performed and the
        confidence is adequate.

        Args:
            report: The Project Capability Report.

        Returns:
            True if the quality rule passes.
        """
        passed = True

        # Check that all five analyses have results.
        if not report.all_analyses_performed:
            dims = report.analysis_dimensions()
            self._findings.append(CapabilityFinding(
                severity=SEVERITY_WARNING,
                code="missing_analyses",
                message=(
                    f"Only {len(dims)} of 5 analysis "
                    f"dimensions were performed: "
                    f"{', '.join(dims) if dims else 'none'}."
                ),
                affected="quality",
                resolution_hint=(
                    "Ensure all five analyses are performed "
                    "with available data sources."
                ),
                category="quality",
            ))

        return passed

    def _validate_dependency_health(
        self, report: ProjectCapabilityReport
    ) -> bool:
        """Validate the dependency health rule.

        Checks that the dependency graph is healthy — no circular
        dependencies, no conflicts, and the health score is
        adequate.

        Args:
            report: The Project Capability Report.

        Returns:
            True if the dependency health rule passes.
        """
        passed = True

        deps = report.dependencies

        # Circular dependencies are always an error.
        if len(deps.circular_dependencies) > 0:
            self._findings.append(CapabilityFinding(
                severity=SEVERITY_ERROR,
                code="circular_dependencies",
                message=(
                    f"{len(deps.circular_dependencies)} "
                    f"circular dependency/dependencies "
                    f"detected. This blocks generation."
                ),
                affected="dependencies",
                resolution_hint=(
                    "Break all circular dependencies before "
                    "proceeding."
                ),
                category="dependency_health",
            ))
            passed = False

        # Conflicts are a warning but block if too many.
        if len(deps.conflicts) > 0:
            self._findings.append(CapabilityFinding(
                severity=SEVERITY_WARNING,
                code="dependency_conflicts",
                message=(
                    f"{len(deps.conflicts)} technology "
                    f"conflict(s) detected."
                ),
                affected="dependencies",
                resolution_hint=(
                    "Resolve conflicting technology selections."
                ),
                category="dependency_health",
            ))

        # Check health score.
        if deps.score < MIN_DEPENDENCY_HEALTH:
            severity = (
                SEVERITY_ERROR
                if deps.score < MIN_DEPENDENCY_HEALTH * 0.5
                else SEVERITY_WARNING
            )
            self._findings.append(CapabilityFinding(
                severity=severity,
                code="low_dependency_health",
                message=(
                    f"Dependency health score ({deps.score:.2f}) "
                    f"is below the minimum "
                    f"({MIN_DEPENDENCY_HEALTH:.2f})."
                ),
                affected="dependencies",
                resolution_hint=(
                    "Resolve dependency issues to improve "
                    "the health score."
                ),
                category="dependency_health",
            ))
            if severity == SEVERITY_ERROR:
                passed = False

        return passed


__all__ = ["QualityGate"]
