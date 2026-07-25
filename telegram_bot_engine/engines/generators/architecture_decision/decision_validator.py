"""
Decision validator — validates every architectural decision.

The :class:`DecisionValidator` is the component that validates that
every architectural decision meets the specification's requirements:

1. **Reason** — every decision must have a reason.
2. **Analysis** — every decision must have an analysis.
3. **Impact** — every decision must have an impact.
4. **Rejected alternatives** — every decision must have at least
   one rejected alternative.

The validator also checks that the decision domains are covered
(layers, modules, services, dependency structure, project layout,
communication, error handling, configuration) and that the selected
value is valid for the domain.

For each check that fails, the validator adds an
:class:`ArchitectureFinding` to the report.  The validator does
**not** fix the issues — it only detects them and records findings.

This module is a pure processing component: it has no side effects
and does not modify the generation context.
"""

from __future__ import annotations

from typing import List, Tuple

from .report_data import (
    ALL_DECISION_DOMAINS,
    ALL_DEP_STRUCTURES,
    ALL_LAYOUTS,
    ALL_COMM_PATTERNS,
    ALL_ERROR_STRATEGIES,
    ALL_CONFIG_STRATEGIES,
    ALL_LAYERS,
    ArchitectureDecision,
    ArchitectureDecisionReport,
    ArchitectureFinding,
    DECISION_COMMUNICATION,
    DECISION_CONFIGURATION,
    DECISION_DEPENDENCY_STRUCTURE,
    DECISION_ERROR_HANDLING,
    DECISION_LAYERS,
    DECISION_PROJECT_LAYOUT,
    PATTERN_BY_SIZE,
    SEVERITY_ERROR,
    SEVERITY_WARNING,
)


class DecisionValidator:
    """Validates every architectural decision.

    The validator checks that every decision has a reason, an
    analysis, an impact, and at least one rejected alternative.
    It also checks that the decision domains are covered and that
    the selected value is valid.
    """

    def validate(
        self,
        report: ArchitectureDecisionReport,
    ) -> Tuple[List[ArchitectureFinding], bool]:
        """Validate the decisions in the report and return the
        findings and the pass/fail status.

        Parameters:
            report: The Architecture Decision Report to validate.

        Returns:
            A tuple ``(findings, passed)`` where ``findings`` is a
            list of :class:`ArchitectureFinding` objects added by
            the validator, and ``passed`` is ``True`` if all
            decisions passed validation.
        """
        findings: List[ArchitectureFinding] = []

        # Check 1: No empty report (no decisions at all).
        if report.decision_count == 0:
            findings.append(ArchitectureFinding(
                severity=SEVERITY_ERROR,
                code="no_decisions",
                message=(
                    "The Architecture Decision Report has no "
                    "decisions. There is nothing to validate."
                ),
                affected="decisions",
                resolution_hint=(
                    "Ensure the architecture selector produces "
                    "decisions."
                ),
                category="validation",
            ))
            return findings, False

        # Check 2: Every decision must have a reason, an analysis,
        # an impact, and at least one rejected alternative.
        for decision in report.decisions:
            if not decision.reason:
                findings.append(ArchitectureFinding(
                    severity=SEVERITY_ERROR,
                    code="missing_reason",
                    message=(
                        f"The decision for domain "
                        f"'{decision.domain}' has no reason."
                    ),
                    affected=decision.domain,
                    resolution_hint=(
                        "Add a reason explaining why this "
                        "decision was made."
                    ),
                    category="validation",
                ))
            if not decision.analysis:
                findings.append(ArchitectureFinding(
                    severity=SEVERITY_ERROR,
                    code="missing_analysis",
                    message=(
                        f"The decision for domain "
                        f"'{decision.domain}' has no analysis."
                    ),
                    affected=decision.domain,
                    resolution_hint=(
                        "Add an analysis supporting this decision."
                    ),
                    category="validation",
                ))
            if not decision.impact:
                findings.append(ArchitectureFinding(
                    severity=SEVERITY_ERROR,
                    code="missing_impact",
                    message=(
                        f"The decision for domain "
                        f"'{decision.domain}' has no impact."
                    ),
                    affected=decision.domain,
                    resolution_hint=(
                        "Add an impact statement describing the "
                        "effect of this decision."
                    ),
                    category="validation",
                ))
            if not decision.rejected_alternatives:
                findings.append(ArchitectureFinding(
                    severity=SEVERITY_ERROR,
                    code="missing_rejected_alternatives",
                    message=(
                        f"The decision for domain "
                        f"'{decision.domain}' has no rejected "
                        f"alternatives. Every decision must "
                        f"consider and reject alternatives."
                    ),
                    affected=decision.domain,
                    resolution_hint=(
                        "Add at least one rejected alternative "
                        "with a reason and impact."
                    ),
                    category="validation",
                ))

        # Check 3: All decision domains must be covered.
        covered_domains = set(report.decision_domains())
        missing_domains = [
            d for d in ALL_DECISION_DOMAINS
            if d not in covered_domains
        ]
        if missing_domains:
            findings.append(ArchitectureFinding(
                severity=SEVERITY_WARNING,
                code="missing_domains",
                message=(
                    f"The following decision domains are not "
                    f"covered: {', '.join(missing_domains)}."
                ),
                affected=", ".join(missing_domains),
                resolution_hint=(
                    "Ensure the architecture selector produces "
                    "decisions for all required domains."
                ),
                category="validation",
            ))

        # Check 4: Validate selected values for specific domains.
        findings.extend(
            self._validate_selected_values(report)
        )

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

    # ----------------------------------------------------------------- #
    # Internal helpers
    # ----------------------------------------------------------------- #

    def _validate_selected_values(
        self,
        report: ArchitectureDecisionReport,
    ) -> List[ArchitectureFinding]:
        """Validate the selected values for specific domains."""
        findings: List[ArchitectureFinding] = []

        # Dependency structure.
        dep_decision = report.get_decision(
            DECISION_DEPENDENCY_STRUCTURE
        )
        if dep_decision:
            if dep_decision.selected not in ALL_DEP_STRUCTURES:
                findings.append(ArchitectureFinding(
                    severity=SEVERITY_ERROR,
                    code="invalid_dependency_structure",
                    message=(
                        f"The selected dependency structure "
                        f"'{dep_decision.selected}' is not a "
                        f"valid value."
                    ),
                    affected=DECISION_DEPENDENCY_STRUCTURE,
                    resolution_hint=(
                        f"Use one of: {', '.join(ALL_DEP_STRUCTURES)}."
                    ),
                    category="validation",
                ))

        # Project layout.
        layout_decision = report.get_decision(DECISION_PROJECT_LAYOUT)
        if layout_decision:
            if layout_decision.selected not in ALL_LAYOUTS:
                findings.append(ArchitectureFinding(
                    severity=SEVERITY_ERROR,
                    code="invalid_project_layout",
                    message=(
                        f"The selected project layout "
                        f"'{layout_decision.selected}' is not a "
                        f"valid value."
                    ),
                    affected=DECISION_PROJECT_LAYOUT,
                    resolution_hint=(
                        f"Use one of: {', '.join(ALL_LAYOUTS)}."
                    ),
                    category="validation",
                ))

        # Communication pattern.
        comm_decision = report.get_decision(DECISION_COMMUNICATION)
        if comm_decision:
            if comm_decision.selected not in ALL_COMM_PATTERNS:
                findings.append(ArchitectureFinding(
                    severity=SEVERITY_ERROR,
                    code="invalid_communication_pattern",
                    message=(
                        f"The selected communication pattern "
                        f"'{comm_decision.selected}' is not a "
                        f"valid value."
                    ),
                    affected=DECISION_COMMUNICATION,
                    resolution_hint=(
                        f"Use one of: {', '.join(ALL_COMM_PATTERNS)}."
                    ),
                    category="validation",
                ))

        # Error handling strategy.
        error_decision = report.get_decision(DECISION_ERROR_HANDLING)
        if error_decision:
            if error_decision.selected not in ALL_ERROR_STRATEGIES:
                findings.append(ArchitectureFinding(
                    severity=SEVERITY_ERROR,
                    code="invalid_error_handling",
                    message=(
                        f"The selected error handling strategy "
                        f"'{error_decision.selected}' is not a "
                        f"valid value."
                    ),
                    affected=DECISION_ERROR_HANDLING,
                    resolution_hint=(
                        f"Use one of: {', '.join(ALL_ERROR_STRATEGIES)}."
                    ),
                    category="validation",
                ))

        # Configuration strategy.
        config_decision = report.get_decision(DECISION_CONFIGURATION)
        if config_decision:
            if config_decision.selected not in ALL_CONFIG_STRATEGIES:
                findings.append(ArchitectureFinding(
                    severity=SEVERITY_ERROR,
                    code="invalid_configuration",
                    message=(
                        f"The selected configuration strategy "
                        f"'{config_decision.selected}' is not a "
                        f"valid value."
                    ),
                    affected=DECISION_CONFIGURATION,
                    resolution_hint=(
                        f"Use one of: {', '.join(ALL_CONFIG_STRATEGIES)}."
                    ),
                    category="validation",
                ))

        # Layers — check that at least the fundamental layers are
        # present.
        layers_decision = report.get_decision(DECISION_LAYERS)
        if layers_decision:
            selected_layers = layers_decision.selected
            for required_layer in (
                LAYER_PRESENTATION := "presentation",
                LAYER_BUSINESS := "business",
            ):
                if required_layer not in selected_layers:
                    findings.append(ArchitectureFinding(
                        severity=SEVERITY_WARNING,
                        code="missing_fundamental_layer",
                        message=(
                            f"The fundamental layer "
                            f"'{required_layer}' is not in the "
                            f"selected layers."
                        ),
                        affected=DECISION_LAYERS,
                        resolution_hint=(
                            "Every project needs at least "
                            "presentation and business layers."
                        ),
                        category="validation",
                    ))

        return findings


__all__ = ["DecisionValidator"]
