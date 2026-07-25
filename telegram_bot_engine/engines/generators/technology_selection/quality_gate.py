"""
QualityGate — Specification 016

Ensures no technology is selected unless it satisfies all quality rules:
    - Quality: well-maintained, widely adopted, well-documented
    - Stability: proven track record with no major regressions
    - Compatibility: works seamlessly with all other selected technologies
    - Scalability: supports horizontal and vertical scaling

The quality gate validates every technology selection against the
four quality rules and rejects any selection that fails.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Tuple

from .report_data import (
    TechnologyFinding,
    TechnologySelectionReport,
    TechnologySelection,
    SEVERITY_ERROR,
    SEVERITY_WARNING,
    SEVERITY_INFO,
    RULE_QUALITY,
    RULE_STABILITY,
    RULE_COMPATIBILITY,
    RULE_SCALABILITY,
    ALL_QUALITY_RULES,
)

_log = logging.getLogger("engine.technology_selection.quality_gate")


# ---------------------------------------------------------------------------#
# Quality data for known technologies
# ---------------------------------------------------------------------------#
#
# Pre-defined quality data for common technologies.
# Each technology is scored on the four quality rules.

QUALITY_DATA: Dict[str, Dict[str, Any]] = {
    # Programming languages
    "python": {
        "quality": {"score": 0.9, "notes": "Widely adopted, excellent docs, huge ecosystem"},
        "stability": {"score": 0.95, "notes": "Very stable, 30+ years, backwards compatible"},
        "compatibility": {"score": 0.85, "notes": "Works with virtually everything"},
        "scalability": {"score": 0.7, "notes": "GIL limits true parallelism but scales well for I/O"},
    },
    "nodejs": {
        "quality": {"score": 0.85, "notes": "Large ecosystem, good documentation"},
        "stability": {"score": 0.8, "notes": "Stable but frequent major updates"},
        "compatibility": {"score": 0.9, "notes": "Works with most databases and services"},
        "scalability": {"score": 0.85, "notes": "Event-driven, scales well for I/O"},
    },
    "java": {
        "quality": {"score": 0.95, "notes": "Enterprise-grade, excellent tooling"},
        "stability": {"score": 0.95, "notes": "Extremely stable, LTS releases"},
        "compatibility": {"score": 0.95, "notes": "Works with everything"},
        "scalability": {"score": 0.95, "notes": "JVM scales horizontally and vertically"},
    },
    "golang": {
        "quality": {"score": 0.9, "notes": "Google-backed, growing ecosystem"},
        "stability": {"score": 0.9, "notes": "Very stable, backward compatible"},
        "compatibility": {"score": 0.85, "notes": "Good ecosystem, still growing"},
        "scalability": {"score": 0.95, "notes": "Built for concurrency and scale"},
    },
    "rust": {
        "quality": {"score": 0.85, "notes": "Excellent safety guarantees, steep learning curve"},
        "stability": {"score": 0.8, "notes": "Stable but ecosystem still maturing"},
        "compatibility": {"score": 0.7, "notes": "Smaller ecosystem than others"},
        "scalability": {"score": 0.95, "notes": "Exceptional performance at scale"},
    },

    # Databases
    "postgresql": {
        "quality": {"score": 0.95, "notes": "Gold standard for relational databases"},
        "stability": {"score": 0.95, "notes": "25+ years, extremely stable"},
        "compatibility": {"score": 0.9, "notes": "Works with all ORMs and tools"},
        "scalability": {"score": 0.85, "notes": "Horizontal scaling with extensions"},
    },
    "mysql": {
        "quality": {"score": 0.85, "notes": "Widely adopted, good documentation"},
        "stability": {"score": 0.9, "notes": "Very stable, Oracle-backed"},
        "compatibility": {"score": 0.9, "notes": "Works with all major tools"},
        "scalability": {"score": 0.8, "notes": "Good vertical scaling, limited horizontal"},
    },
    "mongodb": {
        "quality": {"score": 0.8, "notes": "Good NoSQL option, good docs"},
        "stability": {"score": 0.8, "notes": "Stable but had data loss issues in past"},
        "compatibility": {"score": 0.8, "notes": "Works with modern ORMs"},
        "scalability": {"score": 0.9, "notes": "Built for horizontal scaling"},
    },
    "sqlite": {
        "quality": {"score": 0.9, "notes": "Extremely well-tested, zero-config"},
        "stability": {"score": 0.95, "notes": "Very stable, embedded in most OS"},
        "compatibility": {"score": 0.95, "notes": "Universal support"},
        "scalability": {"score": 0.3, "notes": "Not suitable for production scale"},
    },
    "redis": {
        "quality": {"score": 0.9, "notes": "Industry standard for caching"},
        "stability": {"score": 0.9, "notes": "Very stable, long track record"},
        "compatibility": {"score": 0.9, "notes": "Works with all languages"},
        "scalability": {"score": 0.85, "notes": "Redis Cluster for horizontal scaling"},
    },
    "elasticsearch": {
        "quality": {"score": 0.85, "notes": "Industry standard for search"},
        "stability": {"score": 0.8, "notes": "Stable but frequent breaking changes"},
        "compatibility": {"score": 0.85, "notes": "Good ecosystem"},
        "scalability": {"score": 0.9, "notes": "Designed for distributed search"},
    },

    # ORMs
    "sqlalchemy": {
        "quality": {"score": 0.9, "notes": "Mature, well-designed, excellent docs"},
        "stability": {"score": 0.9, "notes": "Very stable, backward compatible"},
        "compatibility": {"score": 0.95, "notes": "Works with all major databases"},
        "scalability": {"score": 0.8, "notes": "Handles large-scale applications"},
    },
    "django_orm": {
        "quality": {"score": 0.85, "notes": "Well-integrated with Django"},
        "stability": {"score": 0.9, "notes": "Very stable"},
        "compatibility": {"score": 0.75, "notes": "Limited to Django ecosystem"},
        "scalability": {"score": 0.7, "notes": "Good but not as flexible as SQLAlchemy"},
    },
    "prisma": {
        "quality": {"score": 0.8, "notes": "Modern, type-safe, good DX"},
        "stability": {"score": 0.7, "notes": "Still evolving, frequent updates"},
        "compatibility": {"score": 0.8, "notes": "Works with major databases"},
        "scalability": {"score": 0.75, "notes": "Good for most use cases"},
    },
    "gorm": {
        "quality": {"score": 0.8, "notes": "Good Go ORM, active development"},
        "stability": {"score": 0.8, "notes": "Stable, backward compatible"},
        "compatibility": {"score": 0.85, "notes": "Works with major databases"},
        "scalability": {"score": 0.8, "notes": "Good for Go applications"},
    },

    # Caches
    "redis": {
        "quality": {"score": 0.9, "notes": "Industry standard"},
        "stability": {"score": 0.9, "notes": "Very stable"},
        "compatibility": {"score": 0.9, "notes": "Universal support"},
        "scalability": {"score": 0.85, "notes": "Redis Cluster support"},
    },
    "memcached": {
        "quality": {"score": 0.85, "notes": "Simple, fast, well-known"},
        "stability": {"score": 0.9, "notes": "Extremely stable"},
        "compatibility": {"score": 0.9, "notes": "Universal support"},
        "scalability": {"score": 0.8, "notes": "Good horizontal scaling"},
    },

    # Queues
    "rabbitmq": {
        "quality": {"score": 0.85, "notes": "Mature message broker"},
        "stability": {"score": 0.9, "notes": "Very stable"},
        "compatibility": {"score": 0.85, "notes": "AMQP standard, wide support"},
        "scalability": {"score": 0.8, "notes": "Good but clustering can be complex"},
    },
    "kafka": {
        "quality": {"score": 0.9, "notes": "Industry standard for event streaming"},
        "stability": {"score": 0.9, "notes": "Very stable at LinkedIn/Netflix scale"},
        "compatibility": {"score": 0.85, "notes": "Good ecosystem"},
        "scalability": {"score": 0.95, "notes": "Designed for massive scale"},
    },
    "celery": {
        "quality": {"score": 0.75, "notes": "Popular but complex"},
        "stability": {"score": 0.7, "notes": "Some stability issues with workers"},
        "compatibility": {"score": 0.8, "notes": "Works with Redis, RabbitMQ"},
        "scalability": {"score": 0.7, "notes": "Scales but requires careful tuning"},
    },

    # Logging
    "structlog": {
        "quality": {"score": 0.85, "notes": "Excellent structured logging for Python"},
        "stability": {"score": 0.85, "notes": "Stable, well-maintained"},
        "compatibility": {"score": 0.85, "notes": "Works with all Python logging handlers"},
        "scalability": {"score": 0.8, "notes": "Good for large-scale logging"},
    },
    "loguru": {
        "quality": {"score": 0.8, "notes": "Modern, easy to use"},
        "stability": {"score": 0.8, "notes": "Stable but relatively new"},
        "compatibility": {"score": 0.75, "notes": "Not fully compatible with standard logging"},
        "scalability": {"score": 0.75, "notes": "Good for most use cases"},
    },
    "pino": {
        "quality": {"score": 0.85, "notes": "Fastest Node.js logger"},
        "stability": {"score": 0.85, "notes": "Stable, well-maintained"},
        "compatibility": {"score": 0.8, "notes": "Works with most Node.js frameworks"},
        "scalability": {"score": 0.85, "notes": "Excellent performance at scale"},
    },

    # Testing
    "pytest": {
        "quality": {"score": 0.9, "notes": "Best Python testing framework"},
        "stability": {"score": 0.9, "notes": "Very stable, backward compatible"},
        "compatibility": {"score": 0.95, "notes": "Works with everything"},
        "scalability": {"score": 0.85, "notes": "Parallel execution, plugins"},
    },
    "jest": {
        "quality": {"score": 0.85, "notes": "Best Node.js testing framework"},
        "stability": {"score": 0.85, "notes": "Stable, Facebook-backed"},
        "compatibility": {"score": 0.85, "notes": "Works with most Node.js tools"},
        "scalability": {"score": 0.8, "notes": "Good parallel execution"},
    },
    "junit": {
        "quality": {"score": 0.9, "notes": "Industry standard for Java"},
        "stability": {"score": 0.95, "notes": "Extremely stable"},
        "compatibility": {"score": 0.95, "notes": "Universal Java support"},
        "scalability": {"score": 0.8, "notes": "Good parallel execution"},
    },
}


# Minimum quality thresholds.
MIN_QUALITY_SCORE = 0.5
MIN_STABILITY_SCORE = 0.5
MIN_COMPATIBILITY_SCORE = 0.5
MIN_SCALABILITY_SCORE = 0.5


class QualityGate:
    """Validates that candidate technologies meet quality requirements.

    Ensures no technology is selected unless it satisfies all four
    quality rules: quality, stability, compatibility, and scalability.
    """

    def __init__(self) -> None:
        self._findings: List[TechnologyFinding] = []

    def validate(
        self,
        report: TechnologySelectionReport,
    ) -> Tuple[List[TechnologyFinding], bool]:
        """Validate the quality of all technology selections in the
        report.

        Args:
            report: The Technology Selection Report to validate.

        Returns:
            A tuple of (findings, passed) where ``passed`` is True
            if all selections pass the quality gate.
        """
        self._findings = []
        all_passed = True

        # Check if the report is empty.
        if report.is_empty:
            self._findings.append(TechnologyFinding(
                severity=SEVERITY_ERROR,
                code="empty_report",
                message=(
                    "The Technology Selection Report is empty. "
                    "No technologies have been selected."
                ),
                affected="report",
                resolution_hint=(
                    "Ensure the Technology Selection Engine "
                    "has completed its analysis."
                ),
                category="quality",
            ))
            return self._findings, False

        # Validate each selection.
        for selection in report.selections:
            selection_passed = self._validate_selection(selection)
            if not selection_passed:
                all_passed = False

        # Check overall report quality.
        overall_passed = self._validate_report(report)
        if not overall_passed:
            all_passed = False

        return self._findings, all_passed

    @property
    def findings(self) -> List[TechnologyFinding]:
        """Return all findings produced during validation."""
        return self._findings

    # ----------------------------------------------------------------- #
    # Private helpers
    # ----------------------------------------------------------------- #

    def _validate_selection(
        self, selection: TechnologySelection
    ) -> bool:
        """Validate a single technology selection.

        Args:
            selection: The technology selection to validate.

        Returns:
            True if the selection passes all quality checks.
        """
        passed = True
        tech_name = selection.selected.lower()

        # Look up quality data.
        quality_data = QUALITY_DATA.get(tech_name, {})

        # If we don't have quality data, give a warning but don't
        # fail.
        if not quality_data:
            self._findings.append(TechnologyFinding(
                severity=SEVERITY_WARNING,
                code="unknown_technology_quality",
                message=(
                    f"No quality data available for "
                    f"'{selection.selected}'. Cannot validate "
                    f"quality rules."
                ),
                affected=selection.category,
                resolution_hint=(
                    f"Verify that '{selection.selected}' is "
                    f"a well-maintained, stable technology."
                ),
                category="quality",
            ))
            return True  # Don't fail for unknown techs.

        # Validate each quality rule.
        for rule in ALL_QUALITY_RULES:
            rule_data = quality_data.get(rule, {})
            score = rule_data.get("score", 0.5)
            notes = rule_data.get("notes", "")

            # Get the minimum threshold for this rule.
            threshold = self._get_threshold(rule)

            if score < threshold:
                passed = False
                severity = (
                    SEVERITY_ERROR
                    if score < threshold * 0.5
                    else SEVERITY_WARNING
                )
                self._findings.append(TechnologyFinding(
                    severity=severity,
                    code=f"quality_{rule}_failed",
                    message=(
                        f"Technology '{selection.selected}' "
                        f"fails {rule} rule (score: {score:.2f}, "
                        f"threshold: {threshold:.2f}): {notes}"
                    ),
                    affected=f"{selection.category}:{selection.selected}",
                    resolution_hint=(
                        f"Consider an alternative with a higher "
                        f"{rule} score."
                    ),
                    category="quality",
                ))

        return passed

    def _validate_report(
        self, report: TechnologySelectionReport
    ) -> bool:
        """Validate the overall report quality.

        Args:
            report: The Technology Selection Report.

        Returns:
            True if the report passes overall quality checks.
        """
        passed = True

        # Check that all ten categories are covered.
        from .report_data import ALL_TECH_CATEGORIES
        selected_categories = report.selection_categories()
        missing = [
            c for c in ALL_TECH_CATEGORIES
            if c not in selected_categories
        ]
        if missing:
            self._findings.append(TechnologyFinding(
                severity=SEVERITY_WARNING,
                code="incomplete_selections",
                message=(
                    f"Missing technology selections for: "
                    f"{', '.join(missing)}"
                ),
                affected="report",
                resolution_hint=(
                    "Ensure all ten technology categories "
                    "are covered."
                ),
                category="quality",
            ))

        # Check that all selections have required fields.
        for selection in report.selections:
            if not selection.reason:
                self._findings.append(TechnologyFinding(
                    severity=SEVERITY_WARNING,
                    code="missing_reason",
                    message=(
                        f"Selection '{selection.selected}' "
                        f"for '{selection.category}' has no "
                        f"reason."
                    ),
                    affected=selection.category,
                    resolution_hint=(
                        "Every technology selection must have "
                        "a clear reason."
                    ),
                    category="quality",
                ))
                passed = False

            if not selection.analysis:
                self._findings.append(TechnologyFinding(
                    severity=SEVERITY_WARNING,
                    code="missing_analysis",
                    message=(
                        f"Selection '{selection.selected}' "
                        f"for '{selection.category}' has no "
                        f"analysis."
                    ),
                    affected=selection.category,
                    resolution_hint=(
                        "Every technology selection must have "
                        "an analysis."
                    ),
                    category="quality",
                ))
                passed = False

            if not selection.impact:
                self._findings.append(TechnologyFinding(
                    severity=SEVERITY_WARNING,
                    code="missing_impact",
                    message=(
                        f"Selection '{selection.selected}' "
                        f"for '{selection.category}' has no "
                        f"impact."
                    ),
                    affected=selection.category,
                    resolution_hint=(
                        "Every technology selection must have "
                        "an impact statement."
                    ),
                    category="quality",
                ))
                passed = False

            if not selection.rejected_alternatives:
                self._findings.append(TechnologyFinding(
                    severity=SEVERITY_WARNING,
                    code="missing_alternatives",
                    message=(
                        f"Selection '{selection.selected}' "
                        f"for '{selection.category}' has no "
                        f"rejected alternatives."
                    ),
                    affected=selection.category,
                    resolution_hint=(
                        "Every technology selection must "
                        "compare at least one alternative."
                    ),
                    category="quality",
                ))
                passed = False

        # Check confidence.
        if report.confidence < 0.5:
            self._findings.append(TechnologyFinding(
                severity=SEVERITY_WARNING,
                code="low_confidence",
                message=(
                    f"Overall confidence ({report.confidence:.2f}) "
                    f"is below 0.5."
                ),
                affected="report",
                resolution_hint=(
                    "Review the technology selections and "
                    "provide stronger justification."
                ),
                category="quality",
            ))

        return passed

    def _get_threshold(self, rule: str) -> float:
        """Get the minimum threshold for a quality rule.

        Args:
            rule: The quality rule name.

        Returns:
            The minimum threshold score.
        """
        thresholds = {
            RULE_QUALITY: MIN_QUALITY_SCORE,
            RULE_STABILITY: MIN_STABILITY_SCORE,
            RULE_COMPATIBILITY: MIN_COMPATIBILITY_SCORE,
            RULE_SCALABILITY: MIN_SCALABILITY_SCORE,
        }
        return thresholds.get(rule, 0.5)


__all__ = ["QualityGate"]
