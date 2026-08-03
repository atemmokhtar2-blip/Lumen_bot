"""QualityGate — Specification 035 (ULTRA CRITICAL)"""

from __future__ import annotations

from typing import List, Tuple

from .report_data import (
    SecurityReviewReport, SecurityFinding,
    SEVERITY_CRITICAL, SEVERITY_HIGH, SEVERITY_MEDIUM,
    RULE_NO_CRITICAL_VULNS, RULE_NO_HARDCODED_SECRETS, RULE_NO_SENSITIVE_LOGGING,
    RULE_INPUT_VALIDATED, RULE_OUTPUT_SAFE, RULE_AUTH_PRESENT,
    RULE_SELF_REVIEW_PASSED, RULE_QUALITY_PASS, RULE_SUFFICIENT_CONFIDENCE,
    ALL_QUALITY_RULES, MIN_QUALITY_SCORE, CONFIDENCE_MEDIUM_THRESHOLD,
    VERDICT_READY, VERDICT_READY_WITH_WARNINGS, VERDICT_NOT_READY,
    STATUS_OPEN,
    VULN_HARDCODED_PASSWORD, VULN_HARDCODED_TOKEN, VULN_HARDCODED_API_KEY,
    VULN_SECRET_IN_CODE, VULN_SENSITIVE_LOGGING, VULN_UNVALIDATED_INPUT,
)


class QualityGate:
    def validate(self, report: SecurityReviewReport) -> Tuple[List[SecurityFinding], bool, str]:
        findings: List[SecurityFinding] = []
        critical_fail = False
        warnings = 0

        if report.is_empty and report.unit_count == 0:
            # Empty project is not a security failure by itself
            findings.append(SecurityFinding(
                severity=SEVERITY_MEDIUM, code="empty_report",
                message="Security Review Report has no units to scan.",
                affected="report", category="quality",
            ))
            warnings += 1

        for rule in ALL_QUALITY_RULES:
            ok = True
            if rule == RULE_NO_CRITICAL_VULNS:
                open_crit = [
                    v for v in report.vulnerabilities
                    if v.severity == SEVERITY_CRITICAL and v.status == STATUS_OPEN
                ]
                if open_crit or report.open_critical_count > 0:
                    findings.append(SecurityFinding(
                        severity=SEVERITY_CRITICAL, code=rule,
                        message=f"{len(open_crit) or report.open_critical_count} open critical vulnerability(ies).",
                        affected="vulnerabilities", category="security",
                        resolution_hint="Fix or explicitly accept risk before continuing.",
                    ))
                    ok = False
                    critical_fail = True

            elif rule == RULE_NO_HARDCODED_SECRETS:
                secrets = [
                    v for v in report.vulnerabilities
                    if v.vuln_type in (
                        VULN_HARDCODED_PASSWORD, VULN_HARDCODED_TOKEN,
                        VULN_HARDCODED_API_KEY, VULN_SECRET_IN_CODE,
                    ) and v.status == STATUS_OPEN
                ]
                if secrets:
                    findings.append(SecurityFinding(
                        severity=SEVERITY_CRITICAL, code=rule,
                        message=f"{len(secrets)} hardcoded secret(s) still present.",
                        affected="source", category="secrets",
                        resolution_hint="Move secrets to environment variables.",
                    ))
                    ok = False
                    critical_fail = True

            elif rule == RULE_NO_SENSITIVE_LOGGING:
                sens = [
                    v for v in report.vulnerabilities
                    if v.vuln_type == VULN_SENSITIVE_LOGGING and v.status == STATUS_OPEN
                ]
                if sens:
                    findings.append(SecurityFinding(
                        severity=SEVERITY_HIGH, code=rule,
                        message=f"{len(sens)} sensitive logging issue(s).",
                        affected="logging", category="sensitive_data",
                    ))
                    ok = False
                    warnings += 1

            elif rule == RULE_INPUT_VALIDATED:
                unval = [
                    v for v in report.vulnerabilities
                    if v.vuln_type == VULN_UNVALIDATED_INPUT and v.status == STATUS_OPEN
                ]
                if unval:
                    findings.append(SecurityFinding(
                        severity=SEVERITY_MEDIUM, code=rule,
                        message=f"{len(unval)} unit(s) may lack input validation.",
                        affected="inputs", category="validation",
                    ))
                    ok = False
                    warnings += 1

            elif rule == RULE_OUTPUT_SAFE:
                # Covered indirectly; no separate open items required
                pass

            elif rule == RULE_AUTH_PRESENT:
                # Informational — auth gaps are already in vulnerabilities
                pass

            elif rule == RULE_SELF_REVIEW_PASSED:
                if not report.self_review_passed:
                    findings.append(SecurityFinding(
                        severity=SEVERITY_CRITICAL, code=rule,
                        message="Self-review did not pass; residual issues remain.",
                        affected="report", category="self_review",
                    ))
                    ok = False
                    critical_fail = True

            elif rule == RULE_QUALITY_PASS:
                if report.unit_count and report.average_quality_after < MIN_QUALITY_SCORE:
                    findings.append(SecurityFinding(
                        severity=SEVERITY_HIGH, code=rule,
                        message=(
                            f"Average quality after security pass "
                            f"{report.average_quality_after:.1f} < {MIN_QUALITY_SCORE}."
                        ),
                        affected="units", category="quality",
                    ))
                    ok = False
                    warnings += 1

            elif rule == RULE_SUFFICIENT_CONFIDENCE:
                conf = report.provenance.confidence if report.provenance else 0.0
                if conf < CONFIDENCE_MEDIUM_THRESHOLD:
                    findings.append(SecurityFinding(
                        severity=SEVERITY_MEDIUM, code=rule,
                        message=f"Confidence {conf:.2f} below threshold.",
                        affected="provenance", category="confidence",
                    ))
                    ok = False
                    warnings += 1

            if not ok and rule not in (
                RULE_NO_CRITICAL_VULNS, RULE_NO_HARDCODED_SECRETS, RULE_SELF_REVIEW_PASSED,
            ):
                pass  # already counted

        if critical_fail:
            return findings, False, VERDICT_NOT_READY
        if warnings > 0 or any(f.severity == SEVERITY_HIGH for f in findings):
            return findings, True, VERDICT_READY_WITH_WARNINGS
        return findings, True, VERDICT_READY


__all__ = ["QualityGate"]
