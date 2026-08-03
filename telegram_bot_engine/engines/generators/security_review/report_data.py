"""
Security Review Report (Specification 035 — ULTRA CRITICAL).

Intelligent Security Review Engine output artefacts.
Detects and fixes security vulnerabilities without adding features
or changing project logic.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List


SOURCE_CODE_OPTIMIZATION = "code_optimization_report"
SOURCE_BUSINESS_LOGIC = "business_logic_report"
SOURCE_CLASS_GENERATION = "class_generation_report"
SOURCE_FUNCTION_GENERATION = "function_generation_report"
SOURCE_ARCHITECTURE_DECISION = "architecture_decision_report"
SOURCE_PROJECT_CONTEXT = "project_context_report"

ALL_SOURCES = (
    SOURCE_CODE_OPTIMIZATION,
    SOURCE_BUSINESS_LOGIC,
    SOURCE_CLASS_GENERATION,
    SOURCE_FUNCTION_GENERATION,
    SOURCE_ARCHITECTURE_DECISION,
    SOURCE_PROJECT_CONTEXT,
)

SEVERITY_CRITICAL = "critical"
SEVERITY_HIGH = "high"
SEVERITY_MEDIUM = "medium"
SEVERITY_LOW = "low"

# Injection & code execution
VULN_SQL_INJECTION = "sql_injection"
VULN_NOSQL_INJECTION = "nosql_injection"
VULN_COMMAND_INJECTION = "command_injection"
VULN_CODE_INJECTION = "code_injection"
VULN_PATH_TRAVERSAL = "path_traversal"
VULN_UNSAFE_FILE_ACCESS = "unsafe_file_access"
VULN_UNSAFE_DESERIALIZATION = "unsafe_deserialization"
VULN_UNSAFE_REFLECTION = "unsafe_reflection"
VULN_UNSAFE_EVAL = "unsafe_eval"
VULN_UNSAFE_IMPORTS = "unsafe_imports"
VULN_UNSAFE_PARSING = "unsafe_parsing"
VULN_UNSAFE_REGEX = "unsafe_regex"

# Auth
VULN_AUTH_MISSING = "authentication_missing"
VULN_AUTHZ_MISSING = "authorization_missing"
VULN_PERMISSION_CHECK = "permission_check_missing"
VULN_ROLE_VALIDATION = "role_validation_missing"

# Secrets
VULN_HARDCODED_PASSWORD = "hardcoded_password"
VULN_HARDCODED_TOKEN = "hardcoded_token"
VULN_HARDCODED_API_KEY = "hardcoded_api_key"
VULN_SECRET_IN_CODE = "secret_in_code"

# Sensitive data
VULN_SENSITIVE_LOGGING = "sensitive_data_logging"
VULN_SENSITIVE_PRINT = "sensitive_data_print"

# External / validation
VULN_UNVALIDATED_INPUT = "unvalidated_input"
VULN_UNSAFE_OUTPUT = "unsafe_output"
VULN_UNSAFE_HTTP = "unsafe_http"
VULN_UNSAFE_WEBHOOK = "unsafe_webhook"
VULN_UNSAFE_API = "unsafe_api"
VULN_UNSAFE_DB = "unsafe_database_call"

ALL_VULN_TYPES = (
    VULN_SQL_INJECTION, VULN_NOSQL_INJECTION, VULN_COMMAND_INJECTION,
    VULN_CODE_INJECTION, VULN_PATH_TRAVERSAL, VULN_UNSAFE_FILE_ACCESS,
    VULN_UNSAFE_DESERIALIZATION, VULN_UNSAFE_REFLECTION, VULN_UNSAFE_EVAL,
    VULN_UNSAFE_IMPORTS, VULN_UNSAFE_PARSING, VULN_UNSAFE_REGEX,
    VULN_AUTH_MISSING, VULN_AUTHZ_MISSING, VULN_PERMISSION_CHECK,
    VULN_ROLE_VALIDATION,
    VULN_HARDCODED_PASSWORD, VULN_HARDCODED_TOKEN, VULN_HARDCODED_API_KEY,
    VULN_SECRET_IN_CODE,
    VULN_SENSITIVE_LOGGING, VULN_SENSITIVE_PRINT,
    VULN_UNVALIDATED_INPUT, VULN_UNSAFE_OUTPUT,
    VULN_UNSAFE_HTTP, VULN_UNSAFE_WEBHOOK, VULN_UNSAFE_API, VULN_UNSAFE_DB,
)

RULE_NO_CRITICAL_VULNS = "no_critical_vulnerabilities"
RULE_NO_HARDCODED_SECRETS = "no_hardcoded_secrets"
RULE_NO_SENSITIVE_LOGGING = "no_sensitive_logging"
RULE_INPUT_VALIDATED = "input_validated"
RULE_OUTPUT_SAFE = "output_safe"
RULE_AUTH_PRESENT = "auth_present_when_needed"
RULE_SELF_REVIEW_PASSED = "self_review_passed"
RULE_QUALITY_PASS = "quality_pass"
RULE_SUFFICIENT_CONFIDENCE = "sufficient_confidence"

ALL_QUALITY_RULES = (
    RULE_NO_CRITICAL_VULNS,
    RULE_NO_HARDCODED_SECRETS,
    RULE_NO_SENSITIVE_LOGGING,
    RULE_INPUT_VALIDATED,
    RULE_OUTPUT_SAFE,
    RULE_AUTH_PRESENT,
    RULE_SELF_REVIEW_PASSED,
    RULE_QUALITY_PASS,
    RULE_SUFFICIENT_CONFIDENCE,
)

MIN_QUALITY_SCORE = 75.0

CACHE_HIT = "hit"
CACHE_MISS = "miss"
CACHE_DISABLED = "disabled"

CONFIDENCE_HIGH = "high"
CONFIDENCE_MEDIUM = "medium"
CONFIDENCE_LOW = "low"
CONFIDENCE_HIGH_THRESHOLD = 0.85
CONFIDENCE_MEDIUM_THRESHOLD = 0.60

VERDICT_READY = "ready"
VERDICT_READY_WITH_WARNINGS = "ready_with_warnings"
VERDICT_NOT_READY = "not_ready"

ALL_VERDICTS = (VERDICT_READY, VERDICT_READY_WITH_WARNINGS, VERDICT_NOT_READY)

STATUS_OPEN = "open"
STATUS_FIXED = "fixed"
STATUS_ACCEPTED_RISK = "accepted_risk"
STATUS_FALSE_POSITIVE = "false_positive"


@dataclass
class SecurityVulnerability:
    vuln_id: str
    vuln_type: str
    severity: str = SEVERITY_HIGH
    message: str = ""
    location: str = ""
    unit_id: str = ""
    snippet: str = ""
    fix_applied: str = ""
    status: str = STATUS_OPEN
    resolution_hint: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "vuln_id": self.vuln_id,
            "vuln_type": self.vuln_type,
            "severity": self.severity,
            "message": self.message,
            "location": self.location,
            "unit_id": self.unit_id,
            "snippet": self.snippet[:200] if self.snippet else "",
            "fix_applied": self.fix_applied,
            "status": self.status,
            "resolution_hint": self.resolution_hint,
        }


@dataclass
class SecuredUnit:
    unit_id: str
    class_name: str = ""
    method_name: str = ""
    original_code: str = ""
    secured_code: str = ""
    vulns_found: int = 0
    vulns_fixed: int = 0
    quality_before: float = 0.0
    quality_after: float = 0.0
    changed: bool = False
    notes: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "unit_id": self.unit_id,
            "class_name": self.class_name,
            "method_name": self.method_name,
            "original_code": self.original_code,
            "secured_code": self.secured_code,
            "vulns_found": self.vulns_found,
            "vulns_fixed": self.vulns_fixed,
            "quality_before": self.quality_before,
            "quality_after": self.quality_after,
            "changed": self.changed,
            "notes": self.notes,
        }


@dataclass
class SecurityFinding:
    severity: str
    code: str
    message: str
    affected: str = ""
    resolution_hint: str = ""
    category: str = "security"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "severity": self.severity,
            "code": self.code,
            "message": self.message,
            "affected": self.affected,
            "resolution_hint": self.resolution_hint,
            "category": self.category,
        }


@dataclass
class RiskItem:
    risk_id: str
    severity: str
    title: str
    description: str = ""
    affected_units: List[str] = field(default_factory=list)
    mitigation: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "risk_id": self.risk_id,
            "severity": self.severity,
            "title": self.title,
            "description": self.description,
            "affected_units": list(self.affected_units),
            "mitigation": self.mitigation,
        }


@dataclass
class CacheInfo:
    status: str = CACHE_MISS
    key: str = ""
    created_at: str = ""
    hits: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "status": self.status,
            "key": self.key,
            "created_at": self.created_at,
            "hits": self.hits,
        }


@dataclass
class SecurityProvenance:
    engine_name: str = "security_review"
    engine_version: str = "1.0.0"
    sources_used: List[str] = field(default_factory=list)
    sources_missing: List[str] = field(default_factory=list)
    generated_at: str = ""
    confidence: float = 0.0
    confidence_level: str = CONFIDENCE_LOW
    self_review_passed: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "engine_name": self.engine_name,
            "engine_version": self.engine_version,
            "sources_used": list(self.sources_used),
            "sources_missing": list(self.sources_missing),
            "generated_at": self.generated_at,
            "confidence": self.confidence,
            "confidence_level": self.confidence_level,
            "self_review_passed": self.self_review_passed,
        }


@dataclass
class SecurityReviewReport:
    report_id: str = ""
    units: List[SecuredUnit] = field(default_factory=list)
    vulnerabilities: List[SecurityVulnerability] = field(default_factory=list)
    findings: List[SecurityFinding] = field(default_factory=list)
    risks: List[RiskItem] = field(default_factory=list)
    unit_count: int = 0
    vuln_count: int = 0
    critical_count: int = 0
    fixed_count: int = 0
    open_critical_count: int = 0
    average_quality_after: float = 0.0
    self_review_passed: bool = False
    readiness_status: str = VERDICT_NOT_READY
    verdict: str = VERDICT_NOT_READY
    cache_info: CacheInfo = field(default_factory=CacheInfo)
    provenance: SecurityProvenance = field(default_factory=SecurityProvenance)
    metadata: Dict[str, Any] = field(default_factory=dict)
    is_empty: bool = True

    def to_dict(self) -> Dict[str, Any]:
        return {
            "report_id": self.report_id,
            "units": [u.to_dict() for u in self.units],
            "vulnerabilities": [v.to_dict() for v in self.vulnerabilities],
            "findings": [f.to_dict() for f in self.findings],
            "risks": [r.to_dict() for r in self.risks],
            "unit_count": self.unit_count,
            "vuln_count": self.vuln_count,
            "critical_count": self.critical_count,
            "fixed_count": self.fixed_count,
            "open_critical_count": self.open_critical_count,
            "average_quality_after": self.average_quality_after,
            "self_review_passed": self.self_review_passed,
            "readiness_status": self.readiness_status,
            "verdict": self.verdict,
            "cache_info": self.cache_info.to_dict(),
            "provenance": self.provenance.to_dict(),
            "metadata": dict(self.metadata),
            "is_empty": self.is_empty,
        }


__all__ = [
    "SOURCE_CODE_OPTIMIZATION", "SOURCE_BUSINESS_LOGIC",
    "SOURCE_CLASS_GENERATION", "SOURCE_FUNCTION_GENERATION",
    "SOURCE_ARCHITECTURE_DECISION", "SOURCE_PROJECT_CONTEXT", "ALL_SOURCES",
    "SEVERITY_CRITICAL", "SEVERITY_HIGH", "SEVERITY_MEDIUM", "SEVERITY_LOW",
    "VULN_SQL_INJECTION", "VULN_NOSQL_INJECTION", "VULN_COMMAND_INJECTION",
    "VULN_CODE_INJECTION", "VULN_PATH_TRAVERSAL", "VULN_UNSAFE_FILE_ACCESS",
    "VULN_UNSAFE_DESERIALIZATION", "VULN_UNSAFE_REFLECTION", "VULN_UNSAFE_EVAL",
    "VULN_UNSAFE_IMPORTS", "VULN_UNSAFE_PARSING", "VULN_UNSAFE_REGEX",
    "VULN_AUTH_MISSING", "VULN_AUTHZ_MISSING", "VULN_PERMISSION_CHECK",
    "VULN_ROLE_VALIDATION",
    "VULN_HARDCODED_PASSWORD", "VULN_HARDCODED_TOKEN", "VULN_HARDCODED_API_KEY",
    "VULN_SECRET_IN_CODE",
    "VULN_SENSITIVE_LOGGING", "VULN_SENSITIVE_PRINT",
    "VULN_UNVALIDATED_INPUT", "VULN_UNSAFE_OUTPUT",
    "VULN_UNSAFE_HTTP", "VULN_UNSAFE_WEBHOOK", "VULN_UNSAFE_API", "VULN_UNSAFE_DB",
    "ALL_VULN_TYPES",
    "RULE_NO_CRITICAL_VULNS", "RULE_NO_HARDCODED_SECRETS", "RULE_NO_SENSITIVE_LOGGING",
    "RULE_INPUT_VALIDATED", "RULE_OUTPUT_SAFE", "RULE_AUTH_PRESENT",
    "RULE_SELF_REVIEW_PASSED", "RULE_QUALITY_PASS", "RULE_SUFFICIENT_CONFIDENCE",
    "ALL_QUALITY_RULES",
    "MIN_QUALITY_SCORE",
    "CACHE_HIT", "CACHE_MISS", "CACHE_DISABLED",
    "CONFIDENCE_HIGH", "CONFIDENCE_MEDIUM", "CONFIDENCE_LOW",
    "CONFIDENCE_HIGH_THRESHOLD", "CONFIDENCE_MEDIUM_THRESHOLD",
    "VERDICT_READY", "VERDICT_READY_WITH_WARNINGS", "VERDICT_NOT_READY", "ALL_VERDICTS",
    "STATUS_OPEN", "STATUS_FIXED", "STATUS_ACCEPTED_RISK", "STATUS_FALSE_POSITIVE",
    "SecurityVulnerability", "SecuredUnit", "SecurityFinding", "RiskItem",
    "CacheInfo", "SecurityProvenance", "SecurityReviewReport",
]
