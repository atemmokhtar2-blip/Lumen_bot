"""QualityGate — Specification 051 (ULTRA CRITICAL)"""

from __future__ import annotations

from typing import List, Tuple

from .report_data import (
    EnvironmentConfigReport, EnvFinding,
    SEVERITY_CRITICAL, SEVERITY_HIGH, SEVERITY_MEDIUM,
    RULE_NO_SECRETS_IN_REPO, RULE_NO_MISSING_VARS, RULE_NO_UNSAFE_VALUES,
    RULE_CONSISTENCY_OK, RULE_HEALTH_OK, RULE_SELF_VERIFICATION, RULE_QUALITY_PASS,
    ALL_QUALITY_RULES, ENV_PRODUCTION, STATUS_FAILED, STATUS_MISSING,
    VERDICT_READY, VERDICT_READY_WITH_WARNINGS, VERDICT_NOT_READY,
)


class QualityGate:
    def validate(
        self, report: EnvironmentConfigReport
    ) -> Tuple[List[EnvFinding], bool, str]:
        findings: List[EnvFinding] = []
        critical_fail = False
        warnings = 0

        for rule in ALL_QUALITY_RULES:
            if rule == RULE_NO_SECRETS_IN_REPO:
                if not report.secrets_isolated:
                    findings.append(EnvFinding(
                        severity=SEVERITY_CRITICAL, code=rule,
                        message="Secrets detected as stored in project/repo.",
                        affected="secrets", category="security",
                        resolution_hint="Load secrets from environment only.",
                    ))
                    critical_fail = True

            elif rule == RULE_NO_MISSING_VARS:
                if report.missing_count > 0:
                    # Critical if production incomplete
                    prod = next(
                        (p for p in report.profiles if p.name == ENV_PRODUCTION), None
                    )
                    sev = SEVERITY_CRITICAL if (prod and not prod.complete) else SEVERITY_HIGH
                    findings.append(EnvFinding(
                        severity=sev, code=rule,
                        message=f"{report.missing_count} required variable(s) missing.",
                        affected="variables", category="completeness",
                        resolution_hint="Provide all required environment variables.",
                    ))
                    if sev == SEVERITY_CRITICAL:
                        critical_fail = True
                    else:
                        warnings += 1

            elif rule == RULE_NO_UNSAFE_VALUES:
                if report.unsafe_count > 0:
                    findings.append(EnvFinding(
                        severity=SEVERITY_CRITICAL, code=rule,
                        message=f"{report.unsafe_count} unsafe configuration value(s).",
                        affected="variables", category="security",
                    ))
                    critical_fail = True

            elif rule == RULE_CONSISTENCY_OK:
                bad = [p for p in report.profiles if not p.consistent]
                if bad:
                    findings.append(EnvFinding(
                        severity=SEVERITY_HIGH, code=rule,
                        message=f"{len(bad)} environment(s) inconsistent with baseline.",
                        affected=",".join(p.name for p in bad),
                        category="consistency",
                    ))
                    warnings += 1

            elif rule == RULE_HEALTH_OK:
                failed = [
                    h for h in report.health_checks
                    if h.status in (STATUS_FAILED, STATUS_MISSING)
                ]
                if failed:
                    # production health failures are critical
                    sev = (
                        SEVERITY_CRITICAL
                        if report.detected_environment == ENV_PRODUCTION
                        else SEVERITY_HIGH
                    )
                    findings.append(EnvFinding(
                        severity=sev, code=rule,
                        message=f"{len(failed)} health check(s) failed.",
                        affected=",".join(h.target for h in failed),
                        category="health",
                    ))
                    if sev == SEVERITY_CRITICAL:
                        critical_fail = True
                    else:
                        warnings += 1

            elif rule == RULE_SELF_VERIFICATION:
                if not report.self_verification_passed:
                    findings.append(EnvFinding(
                        severity=SEVERITY_CRITICAL, code=rule,
                        message="Self-verification did not pass.",
                        affected="report", category="self_verification",
                    ))
                    critical_fail = True

            elif rule == RULE_QUALITY_PASS:
                if report.score.overall < 70.0:
                    findings.append(EnvFinding(
                        severity=SEVERITY_HIGH, code=rule,
                        message=f"Environment score too low: {report.score.overall}",
                        affected="score", category="score",
                    ))
                    warnings += 1

        if critical_fail:
            return findings, False, VERDICT_NOT_READY
        if warnings > 0 or any(f.severity == SEVERITY_HIGH for f in findings):
            return findings, True, VERDICT_READY_WITH_WARNINGS
        return findings, True, VERDICT_READY


__all__ = ["QualityGate"]
