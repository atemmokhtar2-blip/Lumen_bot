"""
DependencyRiskAnalyzer — Specification 018

Analyzes all libraries and dependencies to detect conflicts or
failure points before project generation begins.

The analyzer detects:
* **Version conflicts** — conflicting version requirements between
  selected technologies.
* **Deprecated libraries** — selected technologies that are
  deprecated or end-of-life.
* **Security vulnerabilities** — dependencies with known security
  vulnerabilities.
* **Excessive dependencies** — too many dependencies, increasing
  maintenance burden and attack surface.
* **Single point of failure** — a critical dependency with no
  fallback or alternative.

The analyzer does not write code, create files, or start the build.
It only analyzes and classifies dependency risks.
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
    DIMENSION_DEPENDENCY,
    SEVERITY_CRITICAL,
    SEVERITY_HIGH,
    SEVERITY_MEDIUM,
    SEVERITY_LOW,
    DEP_RISK_VERSION_CONFLICT,
    DEP_RISK_DEPRECATED,
    DEP_RISK_SECURITY_VULNERABILITY,
    DEP_RISK_TOO_MANY,
    DEP_RISK_SINGLE_POINT,
    PRIORITY_IMMEDIATE,
    PRIORITY_HIGH,
    PRIORITY_MEDIUM,
    PRIORITY_LOW,
)

_log = logging.getLogger("engine.risk_detection.dependency")


# ---------------------------------------------------------------------------#
# Thresholds
# ---------------------------------------------------------------------------#

MAX_DEPENDENCIES = 30          # Above this, dependency count is excessive.
DEPENDENCY_CRITICAL = 50       # Above this, it's critical.
HEALTH_SCORE_LOW = 0.6         # Below this, dependency health is poor.
HEALTH_SCORE_CRITICAL = 0.4    # Below this, it's critical.

# Known deprecated or EOL technologies.
_DEPRECATED_TECH = {
    "python2": "Python 2 is end-of-life since 2020.",
    "django 1": "Django 1.x is end-of-life.",
    "flask 0.12": "Flask 0.12 is outdated.",
    "express 3": "Express 3.x is end-of-life.",
    "angular 1": "AngularJS 1.x is end-of-life.",
    "jquery 2": "jQuery 2.x is outdated.",
    "node 6": "Node.js 6 is end-of-life.",
    "node 8": "Node.js 8 is end-of-life.",
    "node 10": "Node.js 10 is end-of-life.",
    "php 5": "PHP 5 is end-of-life.",
    "ruby 2.3": "Ruby 2.3 is end-of-life.",
}

# Technologies known to have had security advisories.
_HIGH_RISK_TECH = {
    "django 2": "Django 2.x has known security advisories.",
    "flask 0.12": "Flask 0.12 has known vulnerabilities.",
    "node 12": "Node.js 12 has known vulnerabilities.",
    "openssl 1.0": "OpenSSL 1.0 has known vulnerabilities.",
    "log4j 1": "Log4j 1.x has known vulnerabilities.",
}


class DependencyRiskAnalyzer:
    """Detects dependency-level risks.

    The analyzer examines the technology selections and the project
    capability report (dependency health, counts, conflicts) to
    detect:
    * Version conflicts between technologies.
    * Deprecated or end-of-life libraries.
    * Security vulnerabilities in dependencies.
    * Excessive dependency count.
    * Single points of failure in the dependency tree.
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
        """Perform the dependency risk analysis.

        Args:
            cap_data: Project capability data.
            arch_data: Architecture decision data.
            tech_data: Technology selection data.
            req_data: Requirement normalization data.
            kb_data: Knowledge base data.

        Returns:
            A :class:`RiskDimensionResult` for the dependency
            dimension.
        """
        self.findings = []
        self.risks = []

        # ---- Version conflicts ----
        self._detect_version_conflicts(cap_data)

        # ---- Deprecated libraries ----
        self._detect_deprecated(tech_data)

        # ---- Security vulnerabilities ----
        self._detect_security_vulnerabilities(tech_data, cap_data)

        # ---- Excessive dependencies ----
        self._detect_excessive_dependencies(cap_data)

        # ---- Single point of failure ----
        self._detect_single_point_of_failure(arch_data, tech_data)

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
                f"Total dependencies: {cap_data.total_dependencies}."
            )
            details.append(
                f"Dependency health score: "
                f"{cap_data.dependency_health:.2f}."
            )
            details.append(
                f"Dependency conflicts: "
                f"{cap_data.dependency_conflicts}."
            )
            details.append(
                f"Missing dependencies: "
                f"{cap_data.missing_dependencies}."
            )
        details.append(
            f"Dependency risks detected: {len(self.risks)} "
            f"(critical={critical}, high={high}, "
            f"medium={medium}, low={low})."
        )

        summary = (
            f"Dependency risk analysis: {len(self.risks)} "
            f"risk(s) detected."
        )

        return RiskDimensionResult(
            dimension=DIMENSION_DEPENDENCY,
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
    # Version conflicts
    # ----------------------------------------------------------------- #

    def _detect_version_conflicts(
        self, cap_data: ProjectCapabilityData
    ) -> None:
        """Detect version conflicts from the capability report."""
        if not cap_data.available:
            return

        conflicts = cap_data.dependency_conflicts
        if conflicts > 0:
            severity = (
                SEVERITY_CRITICAL
                if conflicts >= 3
                else SEVERITY_HIGH
            )
            priority = (
                PRIORITY_IMMEDIATE
                if severity == SEVERITY_CRITICAL
                else PRIORITY_HIGH
            )

            self._add_risk(
                risk_type=DEP_RISK_VERSION_CONFLICT,
                severity=severity,
                title=f"{conflicts} dependency version conflict(s)",
                description=(
                    f"The capability analysis detected "
                    f"{conflicts} dependency version conflict(s). "
                    f"Conflicting version requirements between "
                    f"selected technologies will cause build or "
                    f"runtime failures."
                ),
                cause=(
                    "Two or more selected technologies require "
                    "incompatible versions of a shared "
                    "transitive dependency."
                ),
                impact=(
                    "Version conflicts cause build failures, "
                    "runtime crashes, or silent bugs. The "
                    "application may not start or may behave "
                    "unpredictably."
                ),
                suggested_fix=(
                    "Pin compatible versions of all dependencies. "
                    "Use a lock file (requirements.txt, "
                    "package-lock.json, poetry.lock) to enforce "
                    "consistent versions. Resolve conflicts by "
                    "upgrading or downgrading conflicting packages."
                ),
                fix_priority=priority,
                affected_components=["dependencies"],
                reasoning=f"conflict_count={conflicts}.",
            )

    # ----------------------------------------------------------------- #
    # Deprecated libraries
    # ----------------------------------------------------------------- #

    def _detect_deprecated(
        self, tech_data: TechnologySelectionData
    ) -> None:
        """Detect deprecated or end-of-life technologies."""
        if not tech_data.available:
            return

        deprecated_found: List[str] = []
        for tech in tech_data.selected_technologies:
            tech_lower = tech.lower()
            for dep_key, reason in _DEPRECATED_TECH.items():
                if dep_key in tech_lower:
                    deprecated_found.append(
                        f"{tech} — {reason}"
                    )

        if deprecated_found:
            severity = (
                SEVERITY_HIGH
                if len(deprecated_found) >= 2
                else SEVERITY_MEDIUM
            )
            priority = (
                PRIORITY_HIGH
                if severity == SEVERITY_HIGH
                else PRIORITY_MEDIUM
            )

            self._add_risk(
                risk_type=DEP_RISK_DEPRECATED,
                severity=severity,
                title=f"{len(deprecated_found)} deprecated library(ies)",
                description=(
                    f"The following selected technologies are "
                    f"deprecated or end-of-life: "
                    f"{'; '.join(deprecated_found)}. "
                    f"Deprecated libraries no longer receive "
                    f"security patches or bug fixes."
                ),
                cause=(
                    "Deprecated or end-of-life technologies were "
                    "selected during the technology selection phase."
                ),
                impact=(
                    "Deprecated libraries do not receive security "
                    "patches. Known vulnerabilities remain "
                    "unfixed. Compatibility with newer runtimes "
                    "and libraries degrades over time."
                ),
                suggested_fix=(
                    "Replace deprecated technologies with their "
                    "modern equivalents (e.g. Python 2 → Python 3, "
                    "AngularJS → Angular, Django 1 → Django 4+). "
                    "Upgrade to the latest stable version of each "
                    "dependency."
                ),
                fix_priority=priority,
                affected_components=[d.split(" — ")[0] for d in deprecated_found],
                reasoning=f"deprecated: {deprecated_found}.",
            )

    # ----------------------------------------------------------------- #
    # Security vulnerabilities
    # ----------------------------------------------------------------- #

    def _detect_security_vulnerabilities(
        self,
        tech_data: TechnologySelectionData,
        cap_data: ProjectCapabilityData,
    ) -> None:
        """Detect known security vulnerabilities in dependencies."""
        # Check technology selections for high-risk technologies.
        vuln_found: List[str] = []
        for tech in tech_data.selected_technologies:
            tech_lower = tech.lower()
            for vuln_key, reason in _HIGH_RISK_TECH.items():
                if vuln_key in tech_lower:
                    vuln_found.append(
                        f"{tech} — {reason}"
                    )

        # Also check capability report for dependency health.
        if cap_data.available and cap_data.dependency_health > 0:
            if cap_data.dependency_health < HEALTH_SCORE_CRITICAL:
                self._add_risk(
                    risk_type=DEP_RISK_SECURITY_VULNERABILITY,
                    severity=SEVERITY_CRITICAL,
                    title="Critical dependency health score",
                    description=(
                        f"The dependency health score is "
                        f"{cap_data.dependency_health:.2f}, "
                        f"below the critical threshold "
                        f"({HEALTH_SCORE_CRITICAL}). The "
                        f"dependency tree likely contains "
                        f"vulnerable or compromised packages."
                    ),
                    cause=(
                        "One or more dependencies have known "
                        "security vulnerabilities or the "
                        "dependency tree is in poor health."
                    ),
                    impact=(
                        "Vulnerable dependencies expose the "
                        "application to known exploits. "
                        "Attackers can use CVEs in dependencies "
                        "to compromise the system."
                    ),
                    suggested_fix=(
                        "Run a vulnerability scanner (pip-audit, "
                        "npm audit, Snyk). Upgrade or replace "
                        "all dependencies with known CVEs. "
                        "Regularly audit the dependency tree."
                    ),
                    fix_priority=PRIORITY_IMMEDIATE,
                    affected_components=["dependencies"],
                    reasoning=(
                        f"dependency_health="
                        f"{cap_data.dependency_health:.2f}."
                    ),
                )
                # If we already added a critical risk for health,
                # don't double-report the individual techs.
                return

        if vuln_found:
            severity = (
                SEVERITY_HIGH
                if len(vuln_found) >= 2
                else SEVERITY_MEDIUM
            )
            priority = (
                PRIORITY_HIGH
                if severity == SEVERITY_HIGH
                else PRIORITY_MEDIUM
            )

            self._add_risk(
                risk_type=DEP_RISK_SECURITY_VULNERABILITY,
                severity=severity,
                title=f"{len(vuln_found)} vulnerable dependencies",
                description=(
                    f"The following technologies have known "
                    f"security advisories: "
                    f"{'; '.join(vuln_found)}. These "
                    f"vulnerabilities may be exploitable in "
                    f"production."
                ),
                cause=(
                    "Technologies with known security "
                    "vulnerabilities were selected."
                ),
                impact=(
                    "Vulnerable dependencies expose the "
                    "application to known exploits (CVEs). "
                    "An attacker can leverage these to gain "
                    "unauthorized access, execute code, or "
                    "cause denial of service."
                ),
                suggested_fix=(
                    "Upgrade to patched versions of the "
                    "affected technologies. Run a dependency "
                    "vulnerability scanner (npm audit, "
                    "pip-audit, Snyk) to find and fix all "
                    "known CVEs."
                ),
                fix_priority=priority,
                affected_components=[
                    v.split(" — ")[0] for v in vuln_found
                ],
                reasoning=f"vulnerable: {vuln_found}.",
            )

    # ----------------------------------------------------------------- #
    # Excessive dependencies
    # ----------------------------------------------------------------- #

    def _detect_excessive_dependencies(
        self, cap_data: ProjectCapabilityData
    ) -> None:
        """Detect excessive dependency count."""
        if not cap_data.available:
            return

        total = cap_data.total_dependencies

        if total > DEPENDENCY_CRITICAL:
            severity = SEVERITY_HIGH
            priority = PRIORITY_HIGH
        elif total > MAX_DEPENDENCIES:
            severity = SEVERITY_MEDIUM
            priority = PRIORITY_MEDIUM
        else:
            return

        self._add_risk(
            risk_type=DEP_RISK_TOO_MANY,
            severity=severity,
            title=f"Excessive dependency count ({total})",
            description=(
                f"The project has {total} dependencies, "
                f"which is "
                f"{'critically ' if total > DEPENDENCY_CRITICAL else ''}"
                f"above the recommended maximum "
                f"({MAX_DEPENDENCIES}). A large dependency tree "
                f"increases maintenance burden, build time, "
                f"and attack surface."
            ),
            cause=(
                "The technology selection phase selected too many "
                "third-party libraries, or the project includes "
                "heavyweight frameworks that pull in many "
                "transitive dependencies."
            ),
            impact=(
                "Excessive dependencies increase build time, "
                "deployment size, maintenance cost, and the "
                "attack surface. Each dependency is a potential "
                "source of bugs, vulnerabilities, and breaking "
                "changes."
            ),
            suggested_fix=(
                "Reduce the dependency count by removing unused "
                "libraries, preferring lightweight alternatives, "
                "and consolidating overlapping dependencies. "
                "Audit transitive dependencies regularly."
            ),
            fix_priority=priority,
            affected_components=["dependencies"],
            reasoning=f"total_dependencies={total}.",
        )

    # ----------------------------------------------------------------- #
    # Single point of failure
    # ----------------------------------------------------------------- #

    def _detect_single_point_of_failure(
        self,
        arch_data: ArchitectureDecisionData,
        tech_data: TechnologySelectionData,
    ) -> None:
        """Detect single points of failure in the dependency tree.

        If the architecture depends on a single database or
        message broker with no fallback, this is a risk.
        """
        if not tech_data.available:
            return

        # Check for single database dependency.
        db_techs = [
            t for t in tech_data.selected_technologies
            if any(
                kw in t.lower()
                for kw in (
                    "postgres", "mysql", "mongodb", "redis",
                    "sqlite", "elasticsearch",
                )
            )
        ]

        has_ha = any(
            kw in t.lower()
            for t in tech_data.selected_technologies
            for kw in (
                "cluster", "replica", "sentinel", "raft",
                "failover", "ha", "high availability",
            )
        )

        if db_techs and not has_ha and arch_data.service_count > 1:
            self._add_risk(
                risk_type=DEP_RISK_SINGLE_POINT,
                severity=SEVERITY_MEDIUM,
                title="Single point of failure in data layer",
                description=(
                    f"The architecture depends on a single "
                    f"{', '.join(db_techs)} instance with no "
                    f"high-availability or failover strategy. "
                    f"If the database goes down, all services "
                    f"that depend on it will fail."
                ),
                cause=(
                    "No high-availability, replication, or "
                    "failover technology was selected for the "
                    "primary data store."
                ),
                impact=(
                    "A single database instance is a single point "
                    "of failure. If it crashes, the entire "
                    "system becomes unavailable. No failover "
                    "means data loss and downtime."
                ),
                suggested_fix=(
                    "Configure replication (primary-replica) or "
                    "clustering for the database. Use Redis "
                    "Sentinel or PostgreSQL streaming replication "
                    "for automatic failover."
                ),
                fix_priority=PRIORITY_MEDIUM,
                affected_components=db_techs,
                reasoning=(
                    f"single db ({', '.join(db_techs)}), "
                    f"no ha tech, "
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
        risk_id = f"dep_{risk_type}_{len(self.risks) + 1}"
        self.risks.append(RiskItem(
            risk_id=risk_id,
            dimension=DIMENSION_DEPENDENCY,
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
            affected="dependency",
            resolution_hint=suggested_fix,
            category="dependency",
        ))

    @staticmethod
    def _calculate_score(risks: List[RiskItem]) -> float:
        """Calculate the dependency risk score (0.0-1.0)."""
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


__all__ = ["DependencyRiskAnalyzer"]
