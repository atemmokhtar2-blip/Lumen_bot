"""
MaintenanceRiskAnalyzer — Specification 018

Detects maintainability risks before project generation begins.

The analyzer detects:
* **High complexity** — the project complexity level is too high
  relative to the module count, making the system hard to maintain.
* **No test strategy** — no testing framework or test strategy
  is selected in the technology stack.
* **No documentation** — no documentation strategy or tooling
  is selected.
* **Tight coupling** — modules are tightly coupled, making changes
  ripple across the system.
* **No monitoring** — no observability or monitoring tools are
  selected, making it hard to diagnose production issues.

The analyzer does not write code, create files, or start the build.
It only detects and classifies maintenance risks.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List

from .data_readers import (
    ProjectCapabilityData,
    ArchitectureDecisionData,
    TechnologySelectionData,
    RequirementNormalizationData,
    KnowledgeData,
)
from .report_data import (
    RiskItem,
    RiskDimensionResult,
    RiskFinding,
    DIMENSION_MAINTENANCE,
    SEVERITY_CRITICAL,
    SEVERITY_HIGH,
    SEVERITY_MEDIUM,
    SEVERITY_LOW,
    MAINT_RISK_COMPLEXITY,
    MAINT_RISK_NO_TESTS,
    MAINT_RISK_NO_DOCS,
    MAINT_RISK_TIGHT_COUPLING,
    MAINT_RISK_NO_MONITORING,
    PRIORITY_IMMEDIATE,
    PRIORITY_HIGH,
    PRIORITY_MEDIUM,
    PRIORITY_LOW,
)

_log = logging.getLogger("engine.risk_detection.maintenance")


# ---------------------------------------------------------------------------#
# Thresholds and keyword sets
# ---------------------------------------------------------------------------#

# Complexity levels (ordered by difficulty).
_COMPLEXITY_RANK = {
    "trivial": 0,
    "simple": 1,
    "moderate": 2,
    "complex": 3,
    "very_complex": 4,
    "extremely_complex": 5,
}

# Technologies that indicate testing strategy.
_TEST_TECH_KEYWORDS = (
    "pytest", "unittest", "jest", "mocha", "cypress",
    "selenium", "test", "testing", "coverage", "nunit",
    "xunit", "rspec",
)

# Technologies that indicate documentation strategy.
_DOC_TECH_KEYWORDS = (
    "sphinx", "mkdocs", "swagger", "openapi", "jsdoc",
    "typedoc", "documentation", "docusaurus",
)

# Technologies that indicate monitoring/observability.
_MONITOR_TECH_KEYWORDS = (
    "prometheus", "grafana", "datadog", "sentry",
    "newrelic", "elastic", "kibana", "zipkin",
    "jaeger", "opentelemetry", "statsd", "logging",
    "logstash", "fluentd",
)

# Coupling threshold: if a module depends on more than this
# many other modules, it's tightly coupled.
_COUPLING_THRESHOLD = 5


class MaintenanceRiskAnalyzer:
    """Detects maintenance-level risks.

    The analyzer examines the project complexity, technology
    selections, and architecture to detect:
    * High complexity relative to module count.
    * Missing test strategy.
    * Missing documentation strategy.
    * Tight coupling between modules.
    * Missing monitoring/observability tools.
    """

    def __init__(self) -> None:
        self.findings: List[RiskFinding] = []
        self.risks: List[RiskItem] = []

    def analyze(
        self,
        cap_data: ProjectCapabilityData,
        arch_data: ArchitectureDecisionData,
        tech_data: TechnologySelectionData,
        req_data: RequirementNormalizationData,
        kb_data: KnowledgeData,
    ) -> RiskDimensionResult:
        """Perform the maintenance risk analysis.

        Args:
            cap_data: Project capability data.
            arch_data: Architecture decision data.
            tech_data: Technology selection data.
            req_data: Requirement normalization data.
            kb_data: Knowledge base data.

        Returns:
            A :class:`RiskDimensionResult` for the maintenance
            dimension.
        """
        self.findings = []
        self.risks = []

        # ---- High complexity ----
        self._detect_high_complexity(cap_data, arch_data)

        # ---- No test strategy ----
        self._detect_no_tests(tech_data, req_data)

        # ---- No documentation ----
        self._detect_no_docs(tech_data)

        # ---- Tight coupling ----
        self._detect_tight_coupling(arch_data, cap_data)

        # ---- No monitoring ----
        self._detect_no_monitoring(tech_data, arch_data)

        # ---- Build the dimension result ----
        critical = sum(
            1 for r in self.risks if r.severity == SEVERITY_CRITICAL
        )
        high = sum(
            1 for r in self.risks if r.severity == SEVERITY_HIGH
        )
        medium = sum(
            1 for r in self.risks if r.severity == SEVERITY_MEDIUM
        )
        low = sum(
            1 for r in self.risks if r.severity == SEVERITY_LOW
        )

        score = self._calculate_score(self.risks)

        details: List[str] = []
        if cap_data.available:
            details.append(
                f"Complexity level: {cap_data.complexity_level}."
            )
            details.append(
                f"Total elements: {cap_data.total_elements}."
            )
        if arch_data.available:
            details.append(
                f"Module count: {arch_data.module_count}."
            )
        details.append(
            f"Maintenance risks detected: {len(self.risks)} "
            f"(critical={critical}, high={high}, "
            f"medium={medium}, low={low})."
        )

        summary = (
            f"Maintenance risk analysis: {len(self.risks)} "
            f"risk(s) detected."
        )

        return RiskDimensionResult(
            dimension=DIMENSION_MAINTENANCE,
            risk_count=len(self.risks),
            critical_count=critical,
            high_count=high,
            medium_count=medium,
            low_count=low,
            score=score,
            summary=summary,
            details=details,
            risks=list(self.risks),
        )

    # ----------------------------------------------------------------- #
    # High complexity
    # ----------------------------------------------------------------- #

    def _detect_high_complexity(
        self,
        cap_data: ProjectCapabilityData,
        arch_data: ArchitectureDecisionData,
    ) -> None:
        """Detect high complexity relative to module count."""
        if not cap_data.available:
            return

        level = cap_data.complexity_level.lower()
        rank = _COMPLEXITY_RANK.get(level, -1)

        if rank < 0:
            return

        if rank >= 4:
            # very_complex or extremely_complex.
            severity = SEVERITY_HIGH
            if rank >= 5:
                severity = SEVERITY_CRITICAL
            priority = (
                PRIORITY_IMMEDIATE
                if severity == SEVERITY_CRITICAL
                else PRIORITY_HIGH
            )
        elif rank >= 3:
            # complex.
            if arch_data.module_count > 0 and arch_data.module_count < 5:
                # Complex with few modules — each module carries
                # a lot of logic.
                severity = SEVERITY_MEDIUM
                priority = PRIORITY_MEDIUM
            else:
                return
        else:
            return

        self._add_risk(
            risk_type=MAINT_RISK_COMPLEXITY,
            severity=severity,
            title=f"High project complexity ({cap_data.complexity_level})",
            description=(
                f"The project complexity is rated "
                f"'{cap_data.complexity_level}' "
                f"with {cap_data.total_elements} total elements "
                f"across {arch_data.module_count} module(s). "
                f"High complexity makes the system difficult to "
                f"understand, test, and maintain."
            ),
            cause=(
                "The architecture is highly complex, possibly "
                "due to many modules, deep dependency trees, or "
                "insufficient decomposition into manageable units."
            ),
            impact=(
                "High complexity increases the cost of changes, "
                "the risk of introducing bugs, and the time "
                "needed for onboarding. It makes testing harder "
                "and debugging more time-consuming."
            ),
            suggested_fix=(
                "Decompose large modules into smaller, focused "
                "units. Reduce the number of dependencies per "
                "module. Apply the single-responsibility "
                "principle. Add comprehensive tests and "
                "documentation to manage complexity."
            ),
            fix_priority=priority,
            affected_components=["architecture", "modules"],
            reasoning=(
                f"complexity={cap_data.complexity_level}, "
                f"rank={rank}, "
                f"modules={arch_data.module_count}."
            ),
        )

    # ----------------------------------------------------------------- #
    # No test strategy
    # ----------------------------------------------------------------- #

    def _detect_no_tests(
        self,
        tech_data: TechnologySelectionData,
        req_data: RequirementNormalizationData,
    ) -> None:
        """Detect missing test strategy."""
        if not tech_data.available:
            return

        has_test_tech = any(
            any(kw in t.lower() for kw in _TEST_TECH_KEYWORDS)
            for t in tech_data.selected_technologies
        )

        # If there are requirements, testing is expected.
        if not has_test_tech and req_data.requirement_count > 0:
            severity = SEVERITY_HIGH
            if req_data.requirement_count > 20:
                severity = SEVERITY_CRITICAL
            priority = (
                PRIORITY_IMMEDIATE
                if severity == SEVERITY_CRITICAL
                else PRIORITY_HIGH
            )

            self._add_risk(
                risk_type=MAINT_RISK_NO_TESTS,
                severity=severity,
                title="No testing framework selected",
                description=(
                    f"The project has "
                    f"{req_data.requirement_count} requirements "
                    f"but no testing framework (pytest, Jest, "
                    f"Mocha) was selected in the technology "
                    f"stack. Without tests, changes cannot be "
                    f"verified safely."
                ),
                cause=(
                    "No testing framework or testing-related "
                    "technology was selected during the "
                    "technology selection phase."
                ),
                impact=(
                    "Without automated tests, regressions go "
                    "undetected, refactoring is risky, and "
                    "bugs reach production. The cost of changes "
                    "increases over time as the codebase grows."
                ),
                suggested_fix=(
                    "Select a testing framework appropriate for "
                    "the language (pytest for Python, Jest for "
                    "JavaScript/TypeScript). Set a minimum code "
                    "coverage target (e.g. 80%). Integrate "
                    "tests into the CI pipeline."
                ),
                fix_priority=priority,
                affected_components=["testing", "ci"],
                reasoning=(
                    f"has_test_tech={has_test_tech}, "
                    f"req_count={req_data.requirement_count}."
                ),
            )

    # ----------------------------------------------------------------- #
    # No documentation
    # ----------------------------------------------------------------- #

    def _detect_no_docs(
        self, tech_data: TechnologySelectionData
    ) -> None:
        """Detect missing documentation strategy."""
        if not tech_data.available:
            return

        has_doc_tech = any(
            any(kw in t.lower() for kw in _DOC_TECH_KEYWORDS)
            for t in tech_data.selected_technologies
        )

        # If there are 10+ selections, documentation is expected.
        if not has_doc_tech and tech_data.selection_count >= 10:
            self._add_risk(
                risk_type=MAINT_RISK_NO_DOCS,
                severity=SEVERITY_MEDIUM,
                title="No documentation tooling selected",
                description=(
                    f"The project has {tech_data.selection_count} "
                    f"technology selections but no documentation "
                    f"tool (Sphinx, MkDocs, Swagger/OpenAPI) was "
                    f"selected. Without documentation tooling, "
                    f"the project will be hard to understand and "
                    f"onboard new developers."
                ),
                cause=(
                    "No documentation generation or API "
                    "documentation technology was selected."
                ),
                impact=(
                    "Without documentation, knowledge stays in "
                    "developers' heads. Onboarding is slow, API "
                    "consumers lack guidance, and the project "
                    "becomes harder to maintain over time."
                ),
                suggested_fix=(
                    "Select a documentation tool: Sphinx or MkDocs "
                    "for project docs, Swagger/OpenAPI for API "
                    "docs, JSDoc or TypeDoc for JS/TS code. "
                    "Generate docs in the CI pipeline."
                ),
                fix_priority=PRIORITY_MEDIUM,
                affected_components=["documentation"],
                reasoning=(
                    f"has_doc_tech={has_doc_tech}, "
                    f"selection_count={tech_data.selection_count}."
                ),
            )

    # ----------------------------------------------------------------- #
    # Tight coupling
    # ----------------------------------------------------------------- #

    def _detect_tight_coupling(
        self,
        arch_data: ArchitectureDecisionData,
        cap_data: ProjectCapabilityData,
    ) -> None:
        """Detect tight coupling between modules."""
        if not arch_data.available:
            return

        # Count modules with more than the coupling threshold
        # of dependencies.
        tightly_coupled: List[str] = []
        for mod in arch_data.modules:
            deps: List[str] = []
            if isinstance(mod, dict):
                deps = mod.get("dependencies", [])
                mod_name = mod.get("name", "unknown")
            elif hasattr(mod, "to_dict"):
                md = mod.to_dict()
                deps = md.get("dependencies", [])
                mod_name = md.get("name", "unknown")
            else:
                continue

            if len(deps) > _COUPLING_THRESHOLD:
                tightly_coupled.append(
                    f"{mod_name} ({len(deps)} deps)"
                )

        if tightly_coupled:
            severity = (
                SEVERITY_HIGH
                if len(tightly_coupled) >= 3
                else SEVERITY_MEDIUM
            )
            priority = (
                PRIORITY_HIGH
                if severity == SEVERITY_HIGH
                else PRIORITY_MEDIUM
            )

            self._add_risk(
                risk_type=MAINT_RISK_TIGHT_COUPLING,
                severity=severity,
                title=f"{len(tightly_coupled)} tightly coupled module(s)",
                description=(
                    f"The following modules have more than "
                    f"{_COUPLING_THRESHOLD} dependencies: "
                    f"{', '.join(tightly_coupled)}. Tight "
                    f"coupling makes changes ripple across the "
                    f"system, increasing maintenance cost."
                ),
                cause=(
                    "Modules depend on too many other modules, "
                    "violating the principle of loose coupling."
                ),
                impact=(
                    "Tight coupling means a change in one module "
                    "affects many others. This increases the "
                    "risk of breaking changes, makes testing "
                    "harder, and reduces code reuse."
                ),
                suggested_fix=(
                    "Apply the dependency inversion principle. "
                    "Introduce interfaces between modules. "
                    "Reduce direct imports; use events or "
                    "message passing for loosely-coupled "
                    "communication."
                ),
                fix_priority=priority,
                affected_components=tightly_coupled,
                reasoning=(
                    f"coupled_modules={len(tightly_coupled)}."
                ),
            )

    # ----------------------------------------------------------------- #
    # No monitoring
    # ----------------------------------------------------------------- #

    def _detect_no_monitoring(
        self,
        tech_data: TechnologySelectionData,
        arch_data: ArchitectureDecisionData,
    ) -> None:
        """Detect missing monitoring/observability tools."""
        if not tech_data.available:
            return

        has_monitor_tech = any(
            any(kw in t.lower() for kw in _MONITOR_TECH_KEYWORDS)
            for t in tech_data.selected_technologies
        )

        # If the project has multiple services, monitoring is
        # expected.
        if not has_monitor_tech and arch_data.service_count > 1:
            self._add_risk(
                risk_type=MAINT_RISK_NO_MONITORING,
                severity=SEVERITY_MEDIUM,
                title="No monitoring/observability tools selected",
                description=(
                    f"The architecture has "
                    f"{arch_data.service_count} services but no "
                    f"monitoring or observability tool "
                    f"(Prometheus, Grafana, Sentry, Datadog) was "
                    f"selected. Without monitoring, production "
                    f"issues will be hard to detect and diagnose."
                ),
                cause=(
                    "No monitoring, logging, or tracing "
                    "technology was selected in the technology "
                    "stack."
                ),
                impact=(
                    "Without monitoring, errors and performance "
                    "degradation go undetected until users "
                    "complain. Mean time to detection (MTTD) "
                    "and mean time to resolution (MTTR) are "
                    "high."
                ),
                suggested_fix=(
                    "Select a monitoring stack: Prometheus + "
                    "Grafana for metrics, Sentry for error "
                    "tracking, OpenTelemetry for distributed "
                    "tracing. Set up alerting on key metrics."
                ),
                fix_priority=PRIORITY_MEDIUM,
                affected_components=["monitoring", "observability"],
                reasoning=(
                    f"has_monitor_tech={has_monitor_tech}, "
                    f"service_count={arch_data.service_count}."
                ),
            )

    # ----------------------------------------------------------------- #
    # Helpers
    # ----------------------------------------------------------------- #

    def _add_risk(
        self,
        risk_type: str,
        severity: str,
        title: str,
        description: str,
        cause: str,
        impact: str,
        suggested_fix: str,
        fix_priority: str,
        affected_components: List[str],
        reasoning: str,
    ) -> None:
        """Add a risk item and a matching finding."""
        risk_id = f"mnt_{risk_type}_{len(self.risks) + 1}"
        self.risks.append(RiskItem(
            risk_id=risk_id,
            dimension=DIMENSION_MAINTENANCE,
            risk_type=risk_type,
            severity=severity,
            title=title,
            description=description,
            cause=cause,
            impact=impact,
            suggested_fix=suggested_fix,
            fix_priority=fix_priority,
            affected_components=list(affected_components),
            reasoning=reasoning,
        ))
        self.findings.append(RiskFinding(
            severity=severity,
            code=risk_id,
            message=title,
            affected="maintenance",
            resolution_hint=suggested_fix,
            category="maintenance",
        ))

    @staticmethod
    def _calculate_score(risks: List[RiskItem]) -> float:
        """Calculate the maintenance risk score (0.0-1.0)."""
        if not risks:
            return 0.0
        scores = {
            SEVERITY_CRITICAL: 1.0,
            SEVERITY_HIGH: 0.75,
            SEVERITY_MEDIUM: 0.5,
            SEVERITY_LOW: 0.25,
        }
        total = sum(scores.get(r.severity, 0.25) for r in risks)
        return min(1.0, total / 2.0)


__all__ = ["MaintenanceRiskAnalyzer"]
