"""
SecurityRiskAnalyzer — Specification 018

Analyzes the design for potential security vulnerabilities *before*
implementation begins.

The analyzer detects:
* **Missing input validation** — no validation strategy for user
  input, API parameters, or data imports.
* **Missing authorization** — no authentication or authorization
  layer in the architecture.
* **Data exposure** — sensitive data stored or transmitted without
  protection.
* **Insecure communication** — inter-service communication without
  encryption.
* **Secrets management** — no strategy for managing secrets
  (API keys, passwords, certificates).

The analyzer does not write code, create files, or start the build.
It only analyzes the design and classifies security risks.
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
    DIMENSION_SECURITY,
    SEVERITY_CRITICAL,
    SEVERITY_HIGH,
    SEVERITY_MEDIUM,
    SEVERITY_LOW,
    SEC_RISK_INPUT_VALIDATION,
    SEC_RISK_AUTHORIZATION,
    SEC_RISK_DATA_EXPOSURE,
    SEC_RISK_INSECURE_COMMUNICATION,
    SEC_RISK_SECRETS_MANAGEMENT,
    PRIORITY_IMMEDIATE,
    PRIORITY_HIGH,
    PRIORITY_MEDIUM,
    PRIORITY_LOW,
)

_log = logging.getLogger("engine.risk_detection.security")


# ---------------------------------------------------------------------------#
# Keyword sets for technology detection
# ---------------------------------------------------------------------------#

_AUTH_TECH_KEYWORDS = (
    "auth", "jwt", "oauth", "saml", "keycloak", "cognito",
    "session", "login", "passport",
)

_CRYPTO_TECH_KEYWORDS = (
    "ssl", "tls", "https", "crypto", "vault", "kms",
    "letsencrypt", "certbot",
)

_SECRET_MGMT_KEYWORDS = (
    "vault", "kms", "secrets", "env", "aws ssm",
    "parameter store", "doppler",
)

_VALIDATION_KEYWORDS = (
    "validate", "validation", "sanitiz", "schema",
    "pydantic", "zod", "joi", "validator",
)

_SENSITIVE_FIELDS = (
    "password", "secret", "token", "key", "credential",
    "ssn", "credit", "card", "api_key", "private",
)


class SecurityRiskAnalyzer:
    """Detects security-level risks in the design.

    The analyzer examines the architecture decisions, technology
    selections, and requirements to detect:
    * Missing input validation.
    * Missing authorization.
    * Data exposure.
    * Insecure communication.
    * Poor secrets management.
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
        """Perform the security risk analysis.

        Args:
            cap_data: Project capability data.
            arch_data: Architecture decision data.
            tech_data: Technology selection data.
            req_data: Requirement normalization data.
            kb_data: Knowledge base data.

        Returns:
            A :class:`RiskDimensionResult` for the security
            dimension.
        """
        self.findings = []
        self.risks = []

        # ---- Missing input validation ----
        self._detect_input_validation(req_data, tech_data)

        # ---- Missing authorization ----
        self._detect_authorization(arch_data, tech_data)

        # ---- Data exposure ----
        self._detect_data_exposure(req_data, tech_data)

        # ---- Insecure communication ----
        self._detect_insecure_communication(arch_data, tech_data)

        # ---- Secrets management ----
        self._detect_secrets_management(tech_data, arch_data)

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
        details.append(
            f"Security risks detected: {len(self.risks)} "
            f"(critical={critical}, high={high}, "
            f"medium={medium}, low={low})."
        )
        if tech_data.available:
            details.append(
                f"Technologies analysed: "
                f"{tech_data.selection_count} selection(s)."
            )
        if arch_data.available:
            details.append(
                f"Architecture modules: "
                f"{arch_data.module_count}."
            )

        summary = (
            f"Security risk analysis: {len(self.risks)} "
            f"risk(s) detected."
        )

        return RiskDimensionResult(
            dimension=DIMENSION_SECURITY,
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
    # Missing input validation
    # ----------------------------------------------------------------- #

    def _detect_input_validation(
        self,
        req_data: RequirementNormalizationData,
        tech_data: TechnologySelectionData,
    ) -> None:
        """Detect missing input validation strategy.

        If the project has functional requirements (which implies
        user input or data handling) but no validation technology
        is selected, this is a security risk.
        """
        if not req_data.available and not tech_data.available:
            return

        # Check if any validation-related tech was selected.
        has_validation_tech = any(
            any(kw in t.lower() for kw in _VALIDATION_KEYWORDS)
            for t in tech_data.selected_technologies
        )

        # Check if any requirements mention input or data handling.
        has_input_req = False
        for req in req_data.requirements:
            req_text = ""
            if isinstance(req, dict):
                req_text = (
                    str(req.get("description", ""))
                    + " "
                    + str(req.get("name", ""))
                    + " "
                    + str(req.get("title", ""))
                ).lower()
            elif hasattr(req, "to_dict"):
                rd = req.to_dict()
                req_text = (
                    str(rd.get("description", ""))
                    + " "
                    + str(rd.get("name", ""))
                    + " "
                    + str(rd.get("title", ""))
                ).lower()
            else:
                req_text = str(req).lower()

            if any(
                kw in req_text
                for kw in (
                    "input", "form", "upload", "user", "api",
                    "request", "parameter", "payload",
                )
            ):
                has_input_req = True
                break

        if has_input_req and not has_validation_tech:
            severity = SEVERITY_HIGH
            priority = PRIORITY_HIGH
            self._add_risk(
                risk_type=SEC_RISK_INPUT_VALIDATION,
                severity=severity,
                title="Missing input validation strategy",
                description=(
                    "The design includes requirements that handle "
                    "user input, API parameters, or data payloads "
                    "but no input validation technology (e.g. "
                    "Pydantic, Zod, Joi) was selected. Unvalidated "
                    "input is a primary attack vector for "
                    "injection, XSS, and data corruption."
                ),
                cause=(
                    "No validation or sanitization technology was "
                    "selected in the technology selection phase."
                ),
                impact=(
                    "Without input validation, the system is "
                    "vulnerable to injection attacks (SQL, NoSQL, "
                    "command), cross-site scripting (XSS), data "
                    "corruption, and unexpected runtime errors."
                ),
                suggested_fix=(
                    "Select an input validation library "
                    "(Pydantic for Python, Zod for TypeScript, Joi "
                    "for Node.js) and enforce schema validation on "
                    "all entry points (API handlers, form "
                    "submissions, file uploads)."
                ),
                fix_priority=priority,
                affected_components=["api", "input_handlers", "forms"],
                reasoning=(
                    f"has_input_req={has_input_req}, "
                    f"has_validation_tech={has_validation_tech}."
                ),
            )

    # ----------------------------------------------------------------- #
    # Missing authorization
    # ----------------------------------------------------------------- #

    def _detect_authorization(
        self,
        arch_data: ArchitectureDecisionData,
        tech_data: TechnologySelectionData,
    ) -> None:
        """Detect missing authentication or authorization layer.

        If the architecture has modules/services but no auth
        technology is selected, this is a critical security risk.
        """
        if not arch_data.available and not tech_data.available:
            return

        has_auth_tech = any(
            any(kw in t.lower() for kw in _AUTH_TECH_KEYWORDS)
            for t in tech_data.selected_technologies
        )

        # Check if any module is related to auth.
        has_auth_module = False
        for mod in arch_data.modules:
            mod_name = ""
            if isinstance(mod, dict):
                mod_name = str(
                    mod.get("name", "") + " " + mod.get("type", "")
                ).lower()
            elif hasattr(mod, "to_dict"):
                md = mod.to_dict()
                mod_name = str(
                    md.get("name", "") + " " + md.get("type", "")
                ).lower()
            if any(
                kw in mod_name for kw in _AUTH_TECH_KEYWORDS
            ):
                has_auth_module = True
                break

        # Check architecture pattern for auth mentions.
        arch_has_auth = (
            "auth" in arch_data.communication.lower()
            or has_auth_module
        )

        if not has_auth_tech and not arch_has_auth:
            # If there are multiple services or external APIs,
            # missing auth is critical.
            if arch_data.service_count > 1:
                severity = SEVERITY_CRITICAL
                priority = PRIORITY_IMMEDIATE
            else:
                severity = SEVERITY_HIGH
                priority = PRIORITY_HIGH

            self._add_risk(
                risk_type=SEC_RISK_AUTHORIZATION,
                severity=severity,
                title="Missing authentication/authorization layer",
                description=(
                    "The architecture does not include any "
                    "authentication or authorization technology "
                    "or module. All endpoints and services would "
                    "be publicly accessible without access "
                    "control."
                ),
                cause=(
                    "No authentication technology (JWT, OAuth, "
                    "Keycloak) or auth module was selected in the "
                    "architecture or technology phases."
                ),
                impact=(
                    "Without authentication, any user can access "
                    "any endpoint, read or modify any data, and "
                    "invoke privileged operations. This is a "
                    "critical security vulnerability."
                ),
                suggested_fix=(
                    "Add an authentication layer (JWT with "
                    "refresh tokens, or OAuth2/OIDC via Keycloak "
                    "or Cognito). Implement role-based access "
                    "control (RBAC) for authorization."
                ),
                fix_priority=priority,
                affected_components=["api", "services", "endpoints"],
                reasoning=(
                    f"has_auth_tech={has_auth_tech}, "
                    f"has_auth_module={has_auth_module}, "
                    f"service_count={arch_data.service_count}."
                ),
            )

    # ----------------------------------------------------------------- #
    # Data exposure
    # ----------------------------------------------------------------- #

    def _detect_data_exposure(
        self,
        req_data: RequirementNormalizationData,
        tech_data: TechnologySelectionData,
    ) -> None:
        """Detect sensitive data exposure risks.

        If requirements mention sensitive data (passwords, tokens,
        credit cards) but no encryption-at-rest or hashing
        technology is selected, this is a security risk.
        """
        if not req_data.available:
            return

        # Check for sensitive data in requirements.
        sensitive_found: List[str] = []
        for req in req_data.requirements:
            req_text = ""
            if isinstance(req, dict):
                req_text = (
                    str(req.get("description", ""))
                    + " "
                    + str(req.get("name", ""))
                    + " "
                    + str(req.get("title", ""))
                ).lower()
            elif hasattr(req, "to_dict"):
                rd = req.to_dict()
                req_text = (
                    str(rd.get("description", ""))
                    + " "
                    + str(rd.get("name", ""))
                    + " "
                    + str(rd.get("title", ""))
                ).lower()
            else:
                req_text = str(req).lower()

            for sf in _SENSITIVE_FIELDS:
                if sf in req_text and sf not in sensitive_found:
                    sensitive_found.append(sf)

        if not sensitive_found:
            return

        # Check for encryption-at-rest / hashing technologies.
        has_encryption = any(
            any(kw in t.lower() for kw in _CRYPTO_TECH_KEYWORDS)
            for t in tech_data.selected_technologies
        )
        has_hashing = any(
            kw in t.lower()
            for t in tech_data.selected_technologies
            for kw in ("bcrypt", "argon2", "hash", "pbkdf2")
        )

        if not has_encryption and not has_hashing:
            severity = SEVERITY_HIGH
            priority = PRIORITY_HIGH
            if len(sensitive_found) >= 3:
                severity = SEVERITY_CRITICAL
                priority = PRIORITY_IMMEDIATE

            self._add_risk(
                risk_type=SEC_RISK_DATA_EXPOSURE,
                severity=severity,
                title="Sensitive data stored without protection",
                description=(
                    f"Requirements mention sensitive data "
                    f"({', '.join(sensitive_found)}) but no "
                    f"encryption-at-rest or password-hashing "
                    f"technology was selected. Sensitive data "
                    f"may be stored in plaintext."
                ),
                cause=(
                    "No encryption or hashing technology was "
                    "selected to protect sensitive data at rest "
                    "or in transit."
                ),
                impact=(
                    "If the database or storage is compromised, "
                    "all sensitive data (passwords, tokens, "
                    "credentials) is exposed in plaintext, "
                    "leading to data breaches and identity theft."
                ),
                suggested_fix=(
                    "Use bcrypt or Argon2 for password hashing. "
                    "Encrypt sensitive data at rest using "
                    "AES-256. Use TLS for data in transit. "
                    "Never store secrets in plaintext."
                ),
                fix_priority=priority,
                affected_components=sensitive_found,
                reasoning=(
                    f"sensitive_fields={sensitive_found}, "
                    f"has_encryption={has_encryption}, "
                    f"has_hashing={has_hashing}."
                ),
            )

    # ----------------------------------------------------------------- #
    # Insecure communication
    # ----------------------------------------------------------------- #

    def _detect_insecure_communication(
        self,
        arch_data: ArchitectureDecisionData,
        tech_data: TechnologySelectionData,
    ) -> None:
        """Detect insecure inter-service communication.

        If the architecture has multiple services that communicate
        but no encryption (TLS/SSL) technology is selected, this is
        a security risk.
        """
        if not arch_data.available:
            return

        # Only relevant if there are multiple communicating services.
        if arch_data.service_count <= 1:
            return

        has_tls = any(
            any(kw in t.lower() for kw in _CRYPTO_TECH_KEYWORDS)
            for t in tech_data.selected_technologies
        )

        comm = arch_data.communication.lower()

        # Check if communication is explicitly insecure.
        insecure_comm = any(
            kw in comm
            for kw in ("http", "plain", "unencrypted", "tcp")
        ) and "https" not in comm and "tls" not in comm

        if not has_tls and insecure_comm:
            severity = SEVERITY_HIGH
            if arch_data.service_count > 3:
                severity = SEVERITY_CRITICAL
            priority = (
                PRIORITY_IMMEDIATE
                if severity == SEVERITY_CRITICAL
                else PRIORITY_HIGH
            )

            self._add_risk(
                risk_type=SEC_RISK_INSECURE_COMMUNICATION,
                severity=severity,
                title="Insecure inter-service communication",
                description=(
                    f"The architecture uses {arch_data.communication} "
                    f"for inter-service communication across "
                    f"{arch_data.service_count} services but no "
                    f"TLS/SSL encryption technology was selected. "
                    f"Data in transit is unencrypted."
                ),
                cause=(
                    "No TLS/SSL certificate or encryption "
                    "technology was selected for inter-service "
                    "communication."
                ),
                impact=(
                    "Unencrypted communication allows "
                    "man-in-the-middle attacks, packet sniffing, "
                    "and data interception. An attacker can read "
                    "or modify data in transit between services."
                ),
                suggested_fix=(
                    "Enable TLS for all inter-service "
                    "communication. Use mTLS (mutual TLS) for "
                    "service-to-service authentication. Obtain "
                    "certificates via Let's Encrypt or a "
                    "certificate authority."
                ),
                fix_priority=priority,
                affected_components=["services", "network"],
                reasoning=(
                    f"comm={arch_data.communication}, "
                    f"has_tls={has_tls}, "
                    f"service_count={arch_data.service_count}."
                ),
            )

    # ----------------------------------------------------------------- #
    # Secrets management
    # ----------------------------------------------------------------- #

    def _detect_secrets_management(
        self,
        tech_data: TechnologySelectionData,
        arch_data: ArchitectureDecisionData,
    ) -> None:
        """Detect poor secrets management strategy.

        If the project uses any cloud or external services (which
        implies API keys, credentials) but no secrets management
        tool is selected, this is a risk.
        """
        if not tech_data.available:
            return

        has_secret_mgmt = any(
            any(kw in t.lower() for kw in _SECRET_MGMT_KEYWORDS)
            for t in tech_data.selected_technologies
        )

        # Check if project uses cloud or external services that
        # require secrets.
        uses_external = any(
            kw in t.lower()
            for t in tech_data.selected_technologies
            for kw in (
                "aws", "azure", "gcp", "stripe", "twilio",
                "sendgrid", "redis", "rabbitmq", "kafka",
                "postgres", "mysql", "mongodb",
            )
        )

        if uses_external and not has_secret_mgmt:
            self._add_risk(
                risk_type=SEC_RISK_SECRETS_MANAGEMENT,
                severity=SEVERITY_MEDIUM,
                title="No secrets management strategy",
                description=(
                    "The project uses external services or "
                    "databases that require credentials, but no "
                    "secrets management tool (Vault, AWS KMS, "
                    "Doppler) was selected. Secrets may be "
                    "hardcoded or stored in plaintext config "
                    "files."
                ),
                cause=(
                    "No secrets management technology was "
                    "selected to securely store and rotate "
                    "credentials, API keys, and certificates."
                ),
                impact=(
                    "Hardcoded secrets in source code or config "
                    "files are exposed in version control, "
                    "container images, and logs. A leaked secret "
                    "can lead to unauthorized access to external "
                    "services and data."
                ),
                suggested_fix=(
                    "Use a secrets manager (HashiCorp Vault, AWS "
                    "Systems Manager Parameter Store, Doppler) "
                    "to store secrets. Inject secrets at runtime "
                    "via environment variables. Never commit "
                    "secrets to version control."
                ),
                fix_priority=PRIORITY_MEDIUM,
                affected_components=["config", "deployment"],
                reasoning=(
                    f"uses_external={uses_external}, "
                    f"has_secret_mgmt={has_secret_mgmt}."
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
        risk_id = f"sec_{risk_type}_{len(self.risks) + 1}"
        self.risks.append(RiskItem(
            risk_id=risk_id,
            dimension=DIMENSION_SECURITY,
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
            affected="security",
            resolution_hint=suggested_fix,
            category="security",
        ))

    @staticmethod
    def _calculate_score(risks: List[RiskItem]) -> float:
        """Calculate the security risk score (0.0-1.0)."""
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


__all__ = ["SecurityRiskAnalyzer"]
