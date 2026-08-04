"""QualityGate — Specification 058 (CRITICAL)"""

from __future__ import annotations

from typing import List, Tuple

from .report_data import (
    CentralLoggingReport, LoggingFinding,
    SEVERITY_CRITICAL, SEVERITY_HIGH, SEVERITY_MEDIUM,
    RULE_CENTRAL_ONLY, RULE_IMMUTABLE, RULE_SENSITIVE_REDACTED,
    RULE_INTEGRITY, RULE_SELF_VERIFICATION, RULE_QUALITY_PASS,
    ALL_QUALITY_RULES,
    VERDICT_READY, VERDICT_READY_WITH_WARNINGS, VERDICT_NOT_READY,
)


class QualityGate:
    def validate(
        self, report: CentralLoggingReport
    ) -> Tuple[List[LoggingFinding], bool, str]:
        findings: List[LoggingFinding] = []
        critical_fail = False
        warnings = 0

        for rule in ALL_QUALITY_RULES:
            if rule == RULE_CENTRAL_ONLY:
                if report.external_log_violations > 0:
                    findings.append(LoggingFinding(
                        severity=SEVERITY_CRITICAL, code=rule,
                        message=(
                            f"{report.external_log_violations} attempt(s) to write "
                            "logs outside the central engine."
                        ),
                        affected="external_logs", category="policy",
                        resolution_hint="Route all logging through central_logging.",
                    ))
                    critical_fail = True

            elif rule == RULE_IMMUTABLE:
                mutable = [e for e in report.entries if not e.immutable]
                if mutable:
                    findings.append(LoggingFinding(
                        severity=SEVERITY_CRITICAL, code=rule,
                        message=f"{len(mutable)} log entr(y/ies) are not immutable.",
                        affected="entries", category="immutability",
                    ))
                    critical_fail = True

            elif rule == RULE_SENSITIVE_REDACTED:
                # If any entry still contains obvious secrets in message
                leaked = [
                    e for e in report.entries
                    if any(
                        f"{k}=" in e.message.lower() and "***redacted***" not in e.message.lower()
                        for k in ("password", "token", "api_key", "secret")
                    )
                ]
                if leaked:
                    findings.append(LoggingFinding(
                        severity=SEVERITY_CRITICAL, code=rule,
                        message=f"{len(leaked)} entr(y/ies) may still expose secrets.",
                        affected=",".join(e.log_id[:8] for e in leaked[:5]),
                        category="security",
                    ))
                    critical_fail = True
                elif report.redacted_count > 0:
                    findings.append(LoggingFinding(
                        severity=SEVERITY_MEDIUM, code=rule,
                        message=f"{report.redacted_count} sensitive value(s) redacted.",
                        affected="entries", category="security",
                    ))
                    warnings += 1

            elif rule == RULE_INTEGRITY:
                if not report.integrity.verified:
                    findings.append(LoggingFinding(
                        severity=SEVERITY_CRITICAL, code=rule,
                        message=report.integrity.message or "Integrity check failed.",
                        affected="checksums", category="integrity",
                    ))
                    critical_fail = True
                if report.integrity.tampered > 0:
                    findings.append(LoggingFinding(
                        severity=SEVERITY_CRITICAL, code=rule,
                        message=f"{report.integrity.tampered} tampered log(s) detected.",
                        affected="checksums", category="integrity",
                    ))
                    critical_fail = True

            elif rule == RULE_SELF_VERIFICATION:
                if not report.self_verification_passed:
                    findings.append(LoggingFinding(
                        severity=SEVERITY_CRITICAL, code=rule,
                        message="Self-verification did not pass.",
                        affected="report", category="self_verification",
                    ))
                    critical_fail = True

            elif rule == RULE_QUALITY_PASS:
                if report.entry_count == 0:
                    findings.append(LoggingFinding(
                        severity=SEVERITY_HIGH, code=rule,
                        message="No log entries produced.",
                        affected="entries", category="quality",
                    ))
                    warnings += 1
                if report.audit_count == 0:
                    findings.append(LoggingFinding(
                        severity=SEVERITY_MEDIUM, code=rule,
                        message="Audit trail is empty.",
                        affected="audit", category="quality",
                    ))
                    warnings += 1

        if critical_fail:
            return findings, False, VERDICT_NOT_READY
        if warnings > 0 or any(f.severity == SEVERITY_HIGH for f in findings):
            return findings, True, VERDICT_READY_WITH_WARNINGS
        return findings, True, VERDICT_READY


__all__ = ["QualityGate"]
