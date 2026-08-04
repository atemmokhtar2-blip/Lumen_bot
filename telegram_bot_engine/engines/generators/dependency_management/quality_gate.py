"""QualityGate — Specification 050 (ULTRA CRITICAL)"""

from __future__ import annotations

from typing import List, Tuple

from .report_data import (
    DependencyManagementReport, DepFinding,
    SEVERITY_CRITICAL, SEVERITY_HIGH, SEVERITY_MEDIUM,
    RULE_NO_INCOMPATIBLE, RULE_NO_UNSAFE, RULE_NO_UNUSED,
    RULE_CONFLICTS_RESOLVED, RULE_LOCKFILE_PRESENT,
    RULE_SELF_VERIFICATION, RULE_QUALITY_PASS, ALL_QUALITY_RULES,
    SEC_VULNERABLE, SEC_UNSAFE,
    VERDICT_READY, VERDICT_READY_WITH_WARNINGS, VERDICT_NOT_READY,
)


class QualityGate:
    def validate(
        self, report: DependencyManagementReport
    ) -> Tuple[List[DepFinding], bool, str]:
        findings: List[DepFinding] = []
        critical_fail = False
        warnings = 0

        for rule in ALL_QUALITY_RULES:
            if rule == RULE_NO_INCOMPATIBLE:
                bad = [d for d in report.dependencies if not d.compatible]
                if bad:
                    findings.append(DepFinding(
                        severity=SEVERITY_CRITICAL, code=rule,
                        message=f"{len(bad)} incompatible dependency(ies).",
                        affected=",".join(d.name for d in bad[:5]),
                        category="compatibility",
                        resolution_hint="Replace or upgrade to compatible versions.",
                    ))
                    critical_fail = True

            elif rule == RULE_NO_UNSAFE:
                unsafe = [
                    s for s in report.security_issues
                    if s.flag in (SEC_VULNERABLE, SEC_UNSAFE)
                ]
                if unsafe:
                    findings.append(DepFinding(
                        severity=SEVERITY_CRITICAL, code=rule,
                        message=f"{len(unsafe)} unsafe/vulnerable package(s).",
                        affected=",".join(s.package for s in unsafe[:5]),
                        category="security",
                        resolution_hint="Remove or upgrade vulnerable packages.",
                    ))
                    critical_fail = True

            elif rule == RULE_NO_UNUSED:
                if report.unused:
                    findings.append(DepFinding(
                        severity=SEVERITY_HIGH, code=rule,
                        message=f"{len(report.unused)} unused package(s) suggested for removal.",
                        affected=",".join(report.unused[:5]),
                        category="unused",
                        resolution_hint="Remove unused dependencies to reduce attack surface.",
                    ))
                    warnings += 1

            elif rule == RULE_CONFLICTS_RESOLVED:
                open_c = [c for c in report.conflicts if not c.resolved]
                if open_c:
                    findings.append(DepFinding(
                        severity=SEVERITY_CRITICAL, code=rule,
                        message=f"{len(open_c)} unresolved dependency conflict(s).",
                        affected=",".join(c.conflict_type for c in open_c[:5]),
                        category="conflict",
                        resolution_hint="Apply suggested resolutions or pin versions.",
                    ))
                    critical_fail = True

            elif rule == RULE_LOCKFILE_PRESENT:
                if report.dependencies and not report.lockfile:
                    findings.append(DepFinding(
                        severity=SEVERITY_HIGH, code=rule,
                        message="Dependencies present but lockfile empty.",
                        affected="lockfile", category="lockfile",
                    ))
                    warnings += 1

            elif rule == RULE_SELF_VERIFICATION:
                if not report.self_verification_passed:
                    findings.append(DepFinding(
                        severity=SEVERITY_CRITICAL, code=rule,
                        message="Self-verification did not pass.",
                        affected="report", category="self_verification",
                    ))
                    critical_fail = True

            elif rule == RULE_QUALITY_PASS:
                if report.health.overall < 70.0:
                    findings.append(DepFinding(
                        severity=SEVERITY_HIGH, code=rule,
                        message=f"Dependency health score too low: {report.health.overall}",
                        affected="health", category="health",
                    ))
                    warnings += 1
                if report.health.security < 80.0:
                    findings.append(DepFinding(
                        severity=SEVERITY_HIGH, code=rule,
                        message=f"Security score below threshold: {report.health.security}",
                        affected="health.security", category="security",
                    ))
                    warnings += 1

        if critical_fail:
            return findings, False, VERDICT_NOT_READY
        if warnings > 0 or any(f.severity == SEVERITY_HIGH for f in findings):
            return findings, True, VERDICT_READY_WITH_WARNINGS
        return findings, True, VERDICT_READY


__all__ = ["QualityGate"]
