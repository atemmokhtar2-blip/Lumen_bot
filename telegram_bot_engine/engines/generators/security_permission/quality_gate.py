"""QualityGate — Specification 060 (MAXIMUM CRITICAL)"""

from __future__ import annotations

from typing import List, Tuple

from .report_data import (
    SecurityPermissionReport, SecurityFinding,
    SEVERITY_CRITICAL, SEVERITY_HIGH, SEVERITY_MEDIUM,
    RULE_LEAST_PRIVILEGE, RULE_NO_ROLE_CHANGE, RULE_ACCESS_VALIDATED,
    RULE_ISOLATION, RULE_NO_UNAUTHORIZED, RULE_SELF_VERIFICATION,
    RULE_QUALITY_PASS, ALL_QUALITY_RULES,
    VERDICT_READY, VERDICT_READY_WITH_WARNINGS, VERDICT_NOT_READY,
)


class QualityGate:
    def validate(
        self, report: SecurityPermissionReport
    ) -> Tuple[List[SecurityFinding], bool, str]:
        findings: List[SecurityFinding] = []
        critical_fail = False
        warnings = 0

        for rule in ALL_QUALITY_RULES:
            if rule == RULE_LEAST_PRIVILEGE:
                # Every role should have explicit denials for non-granted perms
                over_granted = [
                    g for g in report.grants
                    if g.granted and g.reason == "escalation"
                ]
                if over_granted:
                    findings.append(SecurityFinding(
                        severity=SEVERITY_CRITICAL, code=rule,
                        message=f"{len(over_granted)} over-privileged grant(s).",
                        affected=",".join(g.engine_id for g in over_granted[:5]),
                        category="privilege",
                    ))
                    critical_fail = True

            elif rule == RULE_NO_ROLE_CHANGE:
                unlocked = [r for r in report.roles if not r.locked]
                if unlocked:
                    findings.append(SecurityFinding(
                        severity=SEVERITY_CRITICAL, code=rule,
                        message=f"{len(unlocked)} role(s) not locked during execution.",
                        affected=",".join(r.engine_id for r in unlocked[:5]),
                        category="roles",
                    ))
                    critical_fail = True

            elif rule == RULE_ACCESS_VALIDATED:
                if report.engine_count > 0 and not report.access_checks:
                    findings.append(SecurityFinding(
                        severity=SEVERITY_CRITICAL, code=rule,
                        message="No access checks performed.",
                        affected="access_checks", category="access",
                    ))
                    critical_fail = True

            elif rule == RULE_ISOLATION:
                unblocked = [
                    v for v in report.isolation_violations if not v.blocked
                ]
                if unblocked:
                    findings.append(SecurityFinding(
                        severity=SEVERITY_CRITICAL, code=rule,
                        message=f"{len(unblocked)} unblocked isolation breach(es).",
                        affected=",".join(v.source_engine for v in unblocked[:5]),
                        category="isolation",
                    ))
                    critical_fail = True
                elif report.violation_count > 0:
                    findings.append(SecurityFinding(
                        severity=SEVERITY_MEDIUM, code=rule,
                        message=f"{report.violation_count} isolation attempt(s) blocked.",
                        affected="isolation", category="isolation",
                    ))
                    warnings += 1

            elif rule == RULE_NO_UNAUTHORIZED:
                # Unauthorized attempts must be denied (denied_count tracks them)
                if report.unauthorized_attempts > 0 and report.denied_count == 0:
                    findings.append(SecurityFinding(
                        severity=SEVERITY_CRITICAL, code=rule,
                        message="Unauthorized attempts detected but none denied.",
                        affected="access", category="unauthorized",
                    ))
                    critical_fail = True
                elif report.unauthorized_attempts > 0:
                    findings.append(SecurityFinding(
                        severity=SEVERITY_HIGH, code=rule,
                        message=(
                            f"{report.unauthorized_attempts} unauthorized attempt(s) "
                            "detected and handled."
                        ),
                        affected="access", category="unauthorized",
                    ))
                    warnings += 1

            elif rule == RULE_SELF_VERIFICATION:
                if not report.self_verification_passed:
                    findings.append(SecurityFinding(
                        severity=SEVERITY_CRITICAL, code=rule,
                        message="Self-verification did not pass.",
                        affected="report", category="self_verification",
                    ))
                    critical_fail = True

            elif rule == RULE_QUALITY_PASS:
                if report.engine_count == 0:
                    findings.append(SecurityFinding(
                        severity=SEVERITY_CRITICAL, code=rule,
                        message="No engines registered for security.",
                        affected="roles", category="quality",
                    ))
                    critical_fail = True
                unauth = [
                    a for a in report.auth_records if not a.authenticated
                ]
                if unauth:
                    findings.append(SecurityFinding(
                        severity=SEVERITY_CRITICAL, code=rule,
                        message=f"{len(unauth)} engine(s) failed internal auth.",
                        affected=",".join(a.engine_id for a in unauth[:5]),
                        category="auth",
                    ))
                    critical_fail = True
                if not report.audit_trail:
                    findings.append(SecurityFinding(
                        severity=SEVERITY_HIGH, code=rule,
                        message="Security audit trail is empty.",
                        affected="audit", category="quality",
                    ))
                    warnings += 1

        if critical_fail:
            return findings, False, VERDICT_NOT_READY
        if warnings > 0 or any(f.severity == SEVERITY_HIGH for f in findings):
            return findings, True, VERDICT_READY_WITH_WARNINGS
        return findings, True, VERDICT_READY


__all__ = ["QualityGate"]
