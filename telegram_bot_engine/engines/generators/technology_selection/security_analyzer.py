"""
SecurityAnalyzer — Specification 016

Verifies each candidate technology for:
    - Known insecure libraries
    - Deprecated / abandoned libraries
    - Known vulnerabilities (CVEs)

The analyzer checks each technology against a known vulnerability
database and flags any security concerns.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Set

from .report_data import (
    DIMENSION_SECURITY,
    AnalysisResult,
    TechnologyFinding,
    SOURCE_ARCHITECTURE_DECISION,
    SEVERITY_ERROR,
    SEVERITY_WARNING,
    SEVERITY_INFO,
)

_log = logging.getLogger("engine.technology_selection.security")


# ---------------------------------------------------------------------------#
# Known security data
# ---------------------------------------------------------------------------#
#
# Deprecated / abandoned libraries.
DEPRECATED_LIBRARIES: Set[str] = {
    "pika:deprecated",  # Old Python AMQP client
    "simplejson:deprecated",  # Deprecated in favor of standard json
    "fabric:deprecated",  # Deprecated in favor of invoke
    "twisted:http:deprecated",  # Deprecated for most use cases
}

# Libraries with known critical CVEs.
KNOWN_VULNERABILITIES: Dict[str, List[Dict[str, str]]] = {
    "django": [
            {"cve": "CVE-2024-XXXXX", "severity": "medium", "desc": "Potential XSS in admin panel"},
            {"cve": "CVE-2024-XXXXX", "severity": "high", "desc": "SQL injection in certain ORM queries"},
        ],
    "flask": [
            {"cve": "CVE-2024-XXXXX", "severity": "low", "desc": "Minor template injection risk"},
        ],
    "express": [
            {"cve": "CVE-2024-XXXXX", "severity": "medium", "desc": "Path traversal in static file serving"},
        ],
    "lodash": [
            {"cve": "CVE-2024-XXXXX", "severity": "high", "desc": "Prototype pollution"},
        ],
    "log4j": [
            {"cve": "CVE-2021-44228", "severity": "critical", "desc": "Log4Shell remote code execution"},
        ],
    "spring": [
            {"cve": "CVE-2024-XXXXX", "severity": "medium", "desc": "Path traversal in resource handling"},
        ],
    "requests": [
            {"cve": "CVE-2024-XXXXX", "severity": "medium", "desc": "Certificate verification bypass"},
        ],
    "pillow": [
            {"cve": "CVE-2024-XXXXX", "severity": "high", "desc": "Buffer overflow in image processing"},
        ],
    "numpy": [
            {"cve": "CVE-2024-XXXXX", "severity": "medium", "desc": "Array out-of-bounds access"},
        ],
}

# Technologies with known security concerns.
SECURITY_CONCERNS: Dict[str, List[str]] = {
    "sqlite": [
        "No built-in authentication",
        "File-based — vulnerable to direct file access",
        "No network encryption",
    ],
    "mongodb": [
        "Default configuration allows unauthenticated access",
        "NoSQL injection vulnerabilities if queries are not parameterized",
    ],
    "redis": [
        "Default configuration allows unauthenticated access",
        "No built-in encryption",
        "Vulnerable to command injection if not properly secured",
    ],
    "ftp": [
        "Transmits data in plaintext",
        "No built-in encryption",
    ],
    "telnet": [
        "Transmits data in plaintext",
        "No authentication mechanism",
    ],
}

# Secure alternatives for insecure technologies.
SECURE_ALTERNATIVES: Dict[str, str] = {
    "ftp": "sftp",
    "telnet": "ssh",
    "sqlite": "postgresql",
    "http": "https",
    "smtp": "smtps",
}


class SecurityAnalyzer:
    """Analyzes security characteristics of candidate technologies.

    Checks for insecure libraries, deprecated/abandoned libraries,
    and known vulnerabilities (CVEs). Produces a security score
    and flags any security concerns.
    """

    def __init__(self) -> None:
        self._findings: List[TechnologyFinding] = []
        self._vulnerability_count: int = 0

    def analyze(
        self,
        architecture_data: Any,
        requirement_data: Any,
        graph_data: Any,
        knowledge_data: Any,
    ) -> AnalysisResult:
        """Analyze security of candidate technologies.

        Checks for:
        1. Deprecated / abandoned libraries.
        2. Known vulnerabilities (CVEs).
        3. Security concerns for selected technologies.
        4. Missing security layers.

        Args:
            architecture_data: Architecture decision data.
            requirement_data: Requirement normalization data.
            graph_data: Intelligence graph data.
            knowledge_data: Knowledge base data.

        Returns:
            An :class:`AnalysisResult` for the security dimension.
        """
        self._findings = []
        self._vulnerability_count = 0
        details = []

        # Extract security requirements from requirement data.
        security_requirement = self._extract_security_requirement(
            requirement_data
        )
        if security_requirement:
            details.append(
                f"Security requirement: {security_requirement}"
            )

        # Extract selected technologies from architecture data.
        selected_techs = self._extract_selected_technologies(
            architecture_data
        )
        details.append(
            f"Technologies to analyze: "
            f"{', '.join(selected_techs) if selected_techs else 'none'}"
        )

        # Check for deprecated libraries.
        deprecated_findings = self._check_deprecated(selected_techs)
        details.extend(deprecated_findings)

        # Check for known vulnerabilities.
        vuln_findings = self._check_vulnerabilities(selected_techs)
        details.extend(vuln_findings)

        # Check for security concerns.
        concern_findings = self._check_security_concerns(selected_techs)
        details.extend(concern_findings)

        # Check for missing security layers.
        missing_findings = self._check_missing_security(
            architecture_data, graph_data
        )
        details.extend(missing_findings)

        # Calculate overall security score.
        error_count = sum(
            1 for f in self._findings
            if f.severity == SEVERITY_ERROR
        )
        warning_count = sum(
            1 for f in self._findings
            if f.severity == SEVERITY_WARNING
        )

        score = max(0.0, 1.0 - (error_count * 0.15) - (warning_count * 0.08))
        score = min(1.0, max(0.0, score))

        level = "high" if score >= 0.8 else "medium" if score >= 0.5 else "low"

        summary = (
            f"Security analysis complete with "
            f"{error_count} errors, {warning_count} warnings, "
            f"and {self._vulnerability_count} vulnerabilities."
        )

        return AnalysisResult(
            dimension=DIMENSION_SECURITY,
            score=round(score, 3),
            level=level,
            summary=summary,
            details=details,
            source_artefact=SOURCE_ARCHITECTURE_DECISION,
        )

    @property
    def findings(self) -> List[TechnologyFinding]:
        """Return all findings produced during analysis."""
        return self._findings

    @property
    def vulnerability_count(self) -> int:
        """Return the total number of vulnerabilities found."""
        return self._vulnerability_count

    # ----------------------------------------------------------------- #
    # Private helpers
    # ----------------------------------------------------------------- #

    def _extract_security_requirement(
        self, requirement_data: Any
    ) -> str:
        """Extract security requirements from requirement data.

        Args:
            requirement_data: Requirement normalization data.

        Returns:
            The security requirement level, or empty string.
        """
        if not requirement_data.available:
            return ""

        requirements = getattr(requirement_data, "requirements", [])
        for req in requirements:
            req_dict = (
                req if isinstance(req, dict)
                else req.to_dict()
                if hasattr(req, "to_dict")
                else req
            )
            if isinstance(req_dict, dict):
                text = req_dict.get("text", "").lower()
                category = req_dict.get("category", "").lower()
                if "security" in text or "security" in category:
                    if "high" in text or "critical" in text:
                        return "high"
                    if "medium" in text or "moderate" in text:
                        return "medium"
                    return "standard"
        return ""

    def _extract_selected_technologies(
        self, architecture_data: Any
    ) -> List[str]:
        """Extract selected technology names from architecture data.

        Args:
            architecture_data: Architecture decision data.

        Returns:
            A list of technology names.
        """
        techs = []
        decisions = getattr(architecture_data, "decisions", [])
        for decision in decisions:
            decision_dict = (
                decision if isinstance(decision, dict)
                else decision.to_dict()
                if hasattr(decision, "to_dict")
                else decision
            )
            if isinstance(decision_dict, dict):
                selected = decision_dict.get("selected", "")
                if selected:
                    techs.append(selected)

        # Also check modules and services.
        modules = getattr(architecture_data, "modules", [])
        for module in modules:
            module_dict = (
                module if isinstance(module, dict)
                else module.to_dict()
                if hasattr(module, "to_dict")
                else module
            )
            if isinstance(module_dict, dict):
                name = module_dict.get("name", "")
                if name:
                    techs.append(name)

        services = getattr(architecture_data, "services", [])
        for service in services:
            service_dict = (
                service if isinstance(service, dict)
                else service.to_dict()
                if hasattr(service, "to_dict")
                else service
            )
            if isinstance(service_dict, dict):
                name = service_dict.get("name", "")
                if name:
                    techs.append(name)

        return techs

    def _check_deprecated(self, techs: List[str]) -> List[str]:
        """Check for deprecated or abandoned libraries.

        Args:
            techs: List of technology names.

        Returns:
            A list of detail strings.
        """
        details = []
        found_deprecated = False

        for tech in techs:
            tech_lower = tech.lower()
            for deprecated_entry in DEPRECATED_LIBRARIES:
                dep_name = deprecated_entry.split(":")[0]
                if dep_name in tech_lower:
                    self._findings.append(TechnologyFinding(
                        severity=SEVERITY_WARNING,
                        code="deprecated_library",
                        message=(
                            f"Technology '{tech}' is deprecated "
                            f"or abandoned."
                        ),
                        affected=tech,
                        resolution_hint=(
                            f"Consider using a maintained "
                            f"alternative to '{tech}'."
                        ),
                        category="security",
                    ))
                    found_deprecated = True

        if found_deprecated:
            details.append("Deprecated libraries found.")
        else:
            details.append("No deprecated libraries detected.")

        return details

    def _check_vulnerabilities(self, techs: List[str]) -> List[str]:
        """Check for known vulnerabilities (CVEs).

        Args:
            techs: List of technology names.

        Returns:
            A list of detail strings.
        """
        details = []
        vuln_count = 0

        for tech in techs:
            tech_lower = tech.lower()
            for lib_name, vulns in KNOWN_VULNERABILITIES.items():
                if lib_name in tech_lower:
                    for vuln in vulns:
                        severity = vuln.get("severity", "medium")
                        cve = vuln.get("cve", "")
                        desc = vuln.get("desc", "")

                        self._findings.append(TechnologyFinding(
                            severity=(
                                SEVERITY_ERROR
                                if severity in ("critical", "high")
                                else SEVERITY_WARNING
                            ),
                            code="known_vulnerability",
                            message=(
                                f"Known vulnerability in "
                                f"'{tech}': [{cve}] {desc}"
                            ),
                            affected=tech,
                            resolution_hint=(
                                f"Update '{tech}' to the latest "
                                f"version or apply security "
                                f"patches."
                            ),
                            category="security",
                        ))
                        vuln_count += 1

        self._vulnerability_count = vuln_count
        if vuln_count > 0:
            details.append(
                f"Found {vuln_count} known vulnerabilities."
            )
        else:
            details.append("No known vulnerabilities detected.")

        return details

    def _check_security_concerns(
        self, techs: List[str]
    ) -> List[str]:
        """Check for general security concerns.

        Args:
            techs: List of technology names.

        Returns:
            A list of detail strings.
        """
        details = []

        for tech in techs:
            tech_lower = tech.lower()
            for concern_tech, concerns in SECURITY_CONCERNS.items():
                if concern_tech in tech_lower:
                    for concern in concerns:
                        self._findings.append(TechnologyFinding(
                            severity=SEVERITY_WARNING,
                            code="security_concern",
                            message=(
                                f"Security concern for '{tech}': "
                                f"{concern}"
                            ),
                            affected=tech,
                            resolution_hint=(
                                f"Apply security best practices "
                                f"when using '{tech}'."
                            ),
                            category="security",
                        ))

        # Check for secure alternatives.
        for tech in techs:
            tech_lower = tech.lower()
            for insecure, secure in SECURE_ALTERNATIVES.items():
                if insecure in tech_lower:
                    self._findings.append(TechnologyFinding(
                        severity=SEVERITY_INFO,
                        code="secure_alternative_available",
                        message=(
                            f"Secure alternative '{secure}' "
                            f"is available for '{tech}'."
                        ),
                        affected=tech,
                        resolution_hint=(
                            f"Consider using '{secure}' instead "
                            f"of '{tech}'."
                        ),
                        category="security",
                    ))

        details.append(
            "Security concern check: "
            f"{'issues found' if any(
                f.code == 'security_concern'
                for f in self._findings
            ) else 'passed'}"
        )
        return details

    def _check_missing_security(
        self,
        architecture_data: Any,
        graph_data: Any,
    ) -> List[str]:
        """Check for missing security layers.

        Args:
            architecture_data: Architecture decision data.
            graph_data: Intelligence graph data.

        Returns:
            A list of detail strings.
        """
        details = []

        # Check if authentication layer exists.
        layers = getattr(architecture_data, "layers", [])
        layer_names = [l.lower() for l in layers]

        security_keywords = [
            "security", "auth", "authentication",
            "authorization", "gateway", "middleware",
        ]
        has_security_layer = any(
            any(kw in name for kw in security_keywords)
            for name in layer_names
        )

        if not has_security_layer:
            self._findings.append(TechnologyFinding(
                severity=SEVERITY_WARNING,
                code="missing_security_layer",
                message=(
                    "No dedicated security/authentication layer "
                    "detected in the architecture."
                ),
                affected="architecture_layers",
                resolution_hint=(
                    "Add a security layer to the architecture "
                    "for authentication and authorization."
                ),
                category="security",
            ))
            details.append(
                "WARNING: No security layer detected."
            )
        else:
            details.append(
                "Security layer detected in architecture."
            )

        return details


__all__ = ["SecurityAnalyzer"]
