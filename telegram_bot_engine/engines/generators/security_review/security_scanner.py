"""
SecurityScanner — Specification 035 (ULTRA CRITICAL)

Detects security issues in generated source and applies safe fixes.
Does not add features or change business logic beyond hardening.
"""

from __future__ import annotations

import logging
import re
import uuid
from typing import Dict, List, Tuple

from .data_readers import GenericData
from .report_data import (
    SecuredUnit, SecurityVulnerability, RiskItem,
    SEVERITY_CRITICAL, SEVERITY_HIGH, SEVERITY_MEDIUM, SEVERITY_LOW,
    STATUS_OPEN, STATUS_FIXED,
    VULN_SQL_INJECTION, VULN_COMMAND_INJECTION, VULN_CODE_INJECTION,
    VULN_PATH_TRAVERSAL, VULN_UNSAFE_FILE_ACCESS, VULN_UNSAFE_EVAL,
    VULN_UNSAFE_DESERIALIZATION, VULN_UNSAFE_REFLECTION, VULN_UNSAFE_IMPORTS,
    VULN_UNSAFE_REGEX, VULN_HARDCODED_PASSWORD, VULN_HARDCODED_TOKEN,
    VULN_HARDCODED_API_KEY, VULN_SECRET_IN_CODE,
    VULN_SENSITIVE_LOGGING, VULN_SENSITIVE_PRINT,
    VULN_UNVALIDATED_INPUT, VULN_UNSAFE_HTTP, VULN_UNSAFE_DB,
)

_log = logging.getLogger("engine.security_review.scanner")

# Patterns that indicate likely vulnerabilities (conservative heuristics)
_SQL_PATTERN = re.compile(
    r"""(?:execute|executemany|cursor\.execute)\s*\(\s*(?:f["']|["'].*%|["'].*\+|["'].*\.format)""",
    re.IGNORECASE,
)
_CMD_PATTERN = re.compile(
    r"""(?:os\.system|subprocess\.(?:call|run|Popen)|os\.popen)\s*\(\s*(?:f["']|[^"']*\+|.*\.format)""",
    re.IGNORECASE,
)
_EVAL_PATTERN = re.compile(r"""\b(?:eval|exec)\s*\(""", re.IGNORECASE)
_PICKLE_PATTERN = re.compile(r"""\b(?:pickle|cPickle)\.(?:loads?|load)\s*\(""", re.IGNORECASE)
_YAML_UNSAFE = re.compile(r"""yaml\.(?:load)\s*\([^)]*\)""", re.IGNORECASE)
_PATH_JOIN_USER = re.compile(
    r"""(?:open|Path)\s*\(\s*(?:os\.path\.join\s*\([^)]*(?:user|request|input|arg|param)|f["'][^"']*\{)""",
    re.IGNORECASE,
)
_HARDCODED_SECRET = re.compile(
    r"""(?i)(?:password|passwd|secret|api[_-]?key|token|access[_-]?key)\s*=\s*["'][^"']{8,}["']""",
)
_HARDCODED_TOKEN_LIKE = re.compile(
    r"""(?i)(?:Bearer\s+[A-Za-z0-9\-._~+/]+=*|sk-[A-Za-z0-9]{20,}|ghp_[A-Za-z0-9]{20,}|xox[baprs]-[A-Za-z0-9-]{10,})""",
)
_SENSITIVE_LOG = re.compile(
    r"""(?:logger|logging|print)\s*\([^)]*(?:password|token|api_key|secret|cookie|authorization)[^)]*\)""",
    re.IGNORECASE,
)
_REFLECTION = re.compile(r"""\b(?:getattr|setattr|__import__)\s*\([^)]*(?:user|request|input|data)""", re.IGNORECASE)
_UNSAFE_REGEX = re.compile(r"""re\.(?:compile|match|search|findall)\s*\(\s*(?:f["']|[^"']*\+)""", re.IGNORECASE)
_HTTP_NO_TIMEOUT = re.compile(
    r"""(?:requests\.(?:get|post|put|delete|request)|httpx\.(?:get|post)|aiohttp)\s*\([^)]*\)""",
    re.IGNORECASE,
)
_RAW_SQL_FSTRING = re.compile(r"""(?:SELECT|INSERT|UPDATE|DELETE|FROM|WHERE).*\{""", re.IGNORECASE)


class SecurityScanner:
    """Heuristic security scanner + safe auto-fixer."""

    def scan_and_fix(
        self,
        opt_data: GenericData,
        bl_data: GenericData,
        func_data: GenericData,
    ) -> Tuple[List[SecuredUnit], List[SecurityVulnerability], List[RiskItem]]:
        units: List[SecuredUnit] = []
        vulns: List[SecurityVulnerability] = []
        risks: List[RiskItem] = []

        bodies = self._collect_bodies(opt_data, bl_data, func_data)

        for body in bodies:
            unit_id = str(body.get("unit_id") or body.get("method_id") or body.get("name") or uuid.uuid4())
            original = str(
                body.get("secured_code")
                or body.get("optimized_code")
                or body.get("source_code")
                or body.get("code")
                or ""
            )
            class_name = str(body.get("class_name") or "")
            method_name = str(body.get("method_name") or body.get("name") or "")
            q_before = float(body.get("quality_after") or body.get("quality_score") or 60.0)

            if not original.strip():
                units.append(SecuredUnit(
                    unit_id=unit_id,
                    class_name=class_name,
                    method_name=method_name,
                    original_code="",
                    secured_code="",
                    quality_before=q_before,
                    quality_after=q_before,
                    notes="empty unit skipped",
                ))
                continue

            found, fixed_code, unit_vulns = self._analyze_unit(
                unit_id, class_name, method_name, original,
            )
            vulns.extend(unit_vulns)
            fixed_count = sum(1 for v in unit_vulns if v.status == STATUS_FIXED)
            changed = fixed_code != original
            q_after = min(100.0, q_before + (5.0 * fixed_count) - (3.0 * (found - fixed_count)))
            q_after = max(0.0, round(q_after, 1))

            units.append(SecuredUnit(
                unit_id=unit_id,
                class_name=class_name,
                method_name=method_name,
                original_code=original,
                secured_code=fixed_code,
                vulns_found=found,
                vulns_fixed=fixed_count,
                quality_before=q_before,
                quality_after=q_after,
                changed=changed,
                notes=f"found={found} fixed={fixed_count}",
            ))

        # Aggregate residual risks
        open_crit = [v for v in vulns if v.severity == SEVERITY_CRITICAL and v.status == STATUS_OPEN]
        if open_crit:
            risks.append(RiskItem(
                risk_id=str(uuid.uuid4())[:8],
                severity=SEVERITY_CRITICAL,
                title="Open critical security vulnerabilities",
                description=f"{len(open_crit)} critical issue(s) remain unfixed.",
                affected_units=list({v.unit_id for v in open_crit}),
                mitigation="Manual review required before proceeding to next engine.",
            ))

        open_secrets = [
            v for v in vulns
            if v.vuln_type in (
                VULN_HARDCODED_PASSWORD, VULN_HARDCODED_TOKEN,
                VULN_HARDCODED_API_KEY, VULN_SECRET_IN_CODE,
            ) and v.status == STATUS_OPEN
        ]
        if open_secrets:
            risks.append(RiskItem(
                risk_id=str(uuid.uuid4())[:8],
                severity=SEVERITY_HIGH,
                title="Hardcoded secrets detected",
                description=f"{len(open_secrets)} potential secret(s) in source.",
                affected_units=list({v.unit_id for v in open_secrets}),
                mitigation="Move secrets to environment variables or a secret store.",
            ))

        _log.info(
            "SecurityScanner: units=%d vulns=%d open_crit=%d",
            len(units), len(vulns), len(open_crit),
        )
        return units, vulns, risks

    def self_review(
        self,
        units: List[SecuredUnit],
        vulns: List[SecurityVulnerability],
    ) -> Tuple[bool, List[SecurityVulnerability]]:
        """Re-scan secured code to ensure no critical issues remain."""
        residual: List[SecurityVulnerability] = []
        for u in units:
            code = u.secured_code or u.original_code
            if not code.strip():
                continue
            _, _, found = self._analyze_unit(
                u.unit_id, u.class_name, u.method_name, code, fix=False,
            )
            for v in found:
                if v.severity == SEVERITY_CRITICAL and v.status == STATUS_OPEN:
                    residual.append(v)

        # Also count previously open critical that were never fixed
        still_open = [
            v for v in vulns
            if v.severity == SEVERITY_CRITICAL and v.status == STATUS_OPEN
        ]
        passed = len(residual) == 0 and len(still_open) == 0
        return passed, residual

    def _collect_bodies(
        self,
        opt_data: GenericData,
        bl_data: GenericData,
        func_data: GenericData,
    ) -> List[Dict]:
        bodies: List[Dict] = []
        if opt_data.available and opt_data.items:
            for u in opt_data.items:
                bodies.append({
                    "unit_id": u.get("unit_id") or u.get("method_id"),
                    "class_name": u.get("class_name", ""),
                    "method_name": u.get("method_name", ""),
                    "source_code": u.get("secured_code") or u.get("optimized_code") or u.get("source_code") or "",
                    "quality_score": u.get("quality_after") or u.get("quality_before") or 60.0,
                })
        elif bl_data.available and bl_data.items:
            for b in bl_data.items:
                bodies.append({
                    "unit_id": b.get("method_id"),
                    "class_name": b.get("class_name", ""),
                    "method_name": b.get("method_name", ""),
                    "source_code": b.get("source_code", ""),
                    "quality_score": b.get("quality_score", 60.0),
                })
        elif func_data.available and func_data.items:
            for m in func_data.items:
                bodies.append({
                    "unit_id": m.get("method_id") or m.get("name"),
                    "class_name": m.get("class_name", ""),
                    "method_name": m.get("method_name") or m.get("name", ""),
                    "source_code": m.get("source_code") or m.get("signature", ""),
                    "quality_score": m.get("quality_score", 50.0),
                })
        return bodies

    def _analyze_unit(
        self,
        unit_id: str,
        class_name: str,
        method_name: str,
        code: str,
        fix: bool = True,
    ) -> Tuple[int, str, List[SecurityVulnerability]]:
        vulns: List[SecurityVulnerability] = []
        secured = code
        location = f"{class_name}.{method_name}" if class_name else method_name or unit_id

        checks = [
            (_SQL_PATTERN, VULN_SQL_INJECTION, SEVERITY_CRITICAL,
             "Possible SQL injection via string formatting.",
             "Use parameterized queries / bound parameters."),
            (_RAW_SQL_FSTRING, VULN_SQL_INJECTION, SEVERITY_CRITICAL,
             "SQL statement built with f-string / interpolation.",
             "Use parameterized queries."),
            (_CMD_PATTERN, VULN_COMMAND_INJECTION, SEVERITY_CRITICAL,
             "Possible command injection via subprocess/os.",
             "Avoid shell=True; pass argument lists; validate input."),
            (_EVAL_PATTERN, VULN_UNSAFE_EVAL, SEVERITY_CRITICAL,
             "Use of eval/exec detected.",
             "Remove eval/exec; use safe parsers or explicit logic."),
            (_PICKLE_PATTERN, VULN_UNSAFE_DESERIALIZATION, SEVERITY_CRITICAL,
             "Unsafe pickle deserialization.",
             "Prefer json; never unpickle untrusted data."),
            (_YAML_UNSAFE, VULN_UNSAFE_PARSING, SEVERITY_HIGH,
             "yaml.load without SafeLoader.",
             "Use yaml.safe_load()."),
            (_PATH_JOIN_USER, VULN_PATH_TRAVERSAL, SEVERITY_HIGH,
             "Possible path traversal with user-influenced path.",
             "Resolve path and ensure it stays under an allowed root."),
            (_HARDCODED_SECRET, VULN_HARDCODED_PASSWORD, SEVERITY_CRITICAL,
             "Possible hardcoded password/secret.",
             "Load from environment or secret manager."),
            (_HARDCODED_TOKEN_LIKE, VULN_HARDCODED_TOKEN, SEVERITY_CRITICAL,
             "Possible hardcoded token/API key pattern.",
             "Move to environment variables."),
            (_SENSITIVE_LOG, VULN_SENSITIVE_LOGGING, SEVERITY_HIGH,
             "Sensitive data may be logged or printed.",
             "Redact secrets before logging."),
            (_REFLECTION, VULN_UNSAFE_REFLECTION, SEVERITY_HIGH,
             "Dynamic attribute/import driven by external data.",
             "Use explicit allow-lists."),
            (_UNSAFE_REGEX, VULN_UNSAFE_REGEX, SEVERITY_MEDIUM,
             "Regex built from dynamic input (ReDoS risk).",
             "Compile static patterns; limit input size."),
            (_HTTP_NO_TIMEOUT, VULN_UNSAFE_HTTP, SEVERITY_MEDIUM,
             "HTTP client call — ensure timeout and TLS verification.",
             "Always set timeout= and verify=True."),
        ]

        for pattern, vtype, severity, message, hint in checks:
            for m in pattern.finditer(code):
                snippet = m.group(0)[:120]
                vid = f"{vtype}_{unit_id}_{m.start()}"
                status = STATUS_OPEN
                fix_applied = ""

                if fix:
                    new_code, applied = self._try_fix(vtype, secured, m)
                    if applied:
                        secured = new_code
                        status = STATUS_FIXED
                        fix_applied = applied

                vulns.append(SecurityVulnerability(
                    vuln_id=vid,
                    vuln_type=vtype,
                    severity=severity,
                    message=message,
                    location=location,
                    unit_id=unit_id,
                    snippet=snippet,
                    fix_applied=fix_applied,
                    status=status,
                    resolution_hint=hint,
                ))

        # Simple input-validation heuristic: handlers that take text/data without validate/sanitize
        if re.search(r"""(?:message\.text|callback_data|update\.|request\.(?:args|json|form))""", code, re.I):
            if not re.search(r"""(?:validate|sanitize|escape|clean|parse_mode|isinstance)""", code, re.I):
                vulns.append(SecurityVulnerability(
                    vuln_id=f"input_{unit_id}",
                    vuln_type=VULN_UNVALIDATED_INPUT,
                    severity=SEVERITY_MEDIUM,
                    message="External input used without obvious validation.",
                    location=location,
                    unit_id=unit_id,
                    snippet="",
                    status=STATUS_OPEN,
                    resolution_hint="Validate and sanitize all external inputs.",
                ))

        return len(vulns), secured, vulns

    def _try_fix(
        self,
        vtype: str,
        code: str,
        match: re.Match,
    ) -> Tuple[str, str]:
        """Apply conservative, behaviour-preserving fixes where safe."""
        snippet = match.group(0)

        if vtype == VULN_UNSAFE_EVAL:
            # Cannot safely auto-remove eval without breaking intent — leave open
            return code, ""

        if vtype in (VULN_HARDCODED_PASSWORD, VULN_HARDCODED_TOKEN, VULN_HARDCODED_API_KEY, VULN_SECRET_IN_CODE):
            # Replace string literal assignment with os.environ.get
            def repl(m: re.Match) -> str:
                full = m.group(0)
                # extract left side name if possible
                name_m = re.match(
                    r"""(?i)(\w*(?:password|passwd|secret|api[_-]?key|token|access[_-]?key)\w*)\s*=\s*["'][^"']+["']""",
                    full,
                )
                if name_m:
                    var = name_m.group(1)
                    env_key = var.upper()
                    return f'{var} = os.environ.get("{env_key}", "")'
                return full

            new_code, n = _HARDCODED_SECRET.subn(repl, code, count=1)
            if n:
                if "import os" not in new_code and "from os import" not in new_code:
                    new_code = "import os\n" + new_code
                return new_code, "replaced hardcoded secret with os.environ.get"
            # token-like in middle of string — do not auto-edit aggressively
            return code, ""

        if vtype == VULN_SENSITIVE_LOGGING:
            # Comment out or redact — safer to mark only
            return code, ""

        if vtype in (VULN_SQL_INJECTION, VULN_COMMAND_INJECTION):
            # Too risky to auto-rewrite queries; leave for manual
            return code, ""

        if vtype == VULN_UNSAFE_PARSING and "yaml.load" in snippet:
            new_code = code.replace("yaml.load(", "yaml.safe_load(", 1)
            if new_code != code:
                return new_code, "yaml.load → yaml.safe_load"
            return code, ""

        if vtype == VULN_UNSAFE_HTTP:
            # Add timeout if missing inside the call is fragile; skip auto-fix
            return code, ""

        return code, ""


__all__ = ["SecurityScanner"]
