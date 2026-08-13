"""QualityGate — Specification 047 (CRITICAL)"""

from __future__ import annotations

from typing import List, Tuple

from .report_data import (
    GitOperationsReport, GitFinding,
    SEVERITY_CRITICAL, SEVERITY_HIGH, SEVERITY_MEDIUM,
    RULE_USER_VERIFIED, RULE_PERMISSION_OK, RULE_REPO_VERIFIED,
    RULE_DANGEROUS_CONFIRMED, RULE_NO_AUTONOMOUS_HISTORY,
    RULE_SELF_VERIFICATION, RULE_QUALITY_PASS, ALL_QUALITY_RULES,
    STATUS_EXECUTED, STATUS_DENIED, STATUS_FAILED, STATUS_AWAITING_CONFIRMATION,
    DANGEROUS_OPS,
    VERDICT_READY, VERDICT_READY_WITH_WARNINGS, VERDICT_NOT_READY, VERDICT_DENIED,
)


class QualityGate:
    def validate(
        self, report: GitOperationsReport
    ) -> Tuple[List[GitFinding], bool, str]:
        findings: List[GitFinding] = []
        critical_fail = False
        warnings = 0

        executed = [o for o in report.operations if o.status == STATUS_EXECUTED]

        for rule in ALL_QUALITY_RULES:
            if rule == RULE_USER_VERIFIED:
                if executed and not report.user_verified:
                    findings.append(GitFinding(
                        severity=SEVERITY_CRITICAL, code=rule,
                        message="Git ops executed without user verification.",
                        affected="operations", category="auth",
                    ))
                    critical_fail = True

            elif rule == RULE_PERMISSION_OK:
                if executed and not report.permission_ok:
                    findings.append(GitFinding(
                        severity=SEVERITY_CRITICAL, code=rule,
                        message="Git ops executed without sufficient permission.",
                        affected="operations", category="permission",
                    ))
                    critical_fail = True

            elif rule == RULE_REPO_VERIFIED:
                if executed and not report.repo_verified:
                    findings.append(GitFinding(
                        severity=SEVERITY_CRITICAL, code=rule,
                        message="Git ops executed without repository verification.",
                        affected="operations", category="repository",
                    ))
                    critical_fail = True

            elif rule == RULE_DANGEROUS_CONFIRMED:
                for o in executed:
                    if o.dangerous and not o.confirmed:
                        findings.append(GitFinding(
                            severity=SEVERITY_CRITICAL, code=rule,
                            message=f"Dangerous op {o.operation} without confirmation.",
                            affected=o.operation, category="safe_mode",
                            resolution_hint="Require explicit user confirmation.",
                        ))
                        critical_fail = True

            elif rule == RULE_NO_AUTONOMOUS_HISTORY:
                # Conflicts must not be auto-resolved
                auto = [c for c in report.conflicts if c.resolved and not c.user_approved]
                if auto:
                    findings.append(GitFinding(
                        severity=SEVERITY_CRITICAL, code=rule,
                        message="Conflict auto-resolved without user approval.",
                        affected="conflicts", category="history",
                    ))
                    critical_fail = True

            elif rule == RULE_SELF_VERIFICATION:
                if not report.self_verification_passed:
                    findings.append(GitFinding(
                        severity=SEVERITY_CRITICAL, code=rule,
                        message="Self-verification did not pass.",
                        affected="report", category="self_verification",
                    ))
                    critical_fail = True

            elif rule == RULE_QUALITY_PASS:
                failed = [o for o in report.operations if o.status == STATUS_FAILED]
                if failed:
                    findings.append(GitFinding(
                        severity=SEVERITY_HIGH, code=rule,
                        message=f"{len(failed)} git operation(s) failed.",
                        affected="operations", category="execution",
                    ))
                    warnings += 1
                awaiting = [
                    o for o in report.operations
                    if o.status == STATUS_AWAITING_CONFIRMATION
                ]
                if awaiting:
                    findings.append(GitFinding(
                        severity=SEVERITY_MEDIUM, code=rule,
                        message=f"{len(awaiting)} op(s) awaiting user confirmation.",
                        affected="operations", category="safe_mode",
                    ))
                    warnings += 1

        if critical_fail:
            return findings, False, VERDICT_NOT_READY
        if report.denied_count and not executed:
            return findings, True, VERDICT_DENIED
        if warnings > 0 or any(f.severity == SEVERITY_HIGH for f in findings):
            return findings, True, VERDICT_READY_WITH_WARNINGS
        return findings, True, VERDICT_READY


__all__ = ["QualityGate"]
