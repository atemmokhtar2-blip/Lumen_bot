"""QualityGate — Specification 059 (CRITICAL)"""

from __future__ import annotations

from typing import List, Tuple

from .report_data import (
    ConfigurationManagementReport, ConfigFinding,
    SEVERITY_CRITICAL, SEVERITY_HIGH, SEVERITY_MEDIUM,
    RULE_CENTRAL_ONLY, RULE_VALIDATED, RULE_VERSIONED, RULE_PROTECTED,
    RULE_SELF_VERIFICATION, RULE_QUALITY_PASS, ALL_QUALITY_RULES,
    VERDICT_READY, VERDICT_READY_WITH_WARNINGS, VERDICT_NOT_READY,
    ISSUE_MISSING,
)


class QualityGate:
    def validate(
        self, report: ConfigurationManagementReport
    ) -> Tuple[List[ConfigFinding], bool, str]:
        findings: List[ConfigFinding] = []
        critical_fail = False
        warnings = 0

        for rule in ALL_QUALITY_RULES:
            if rule == RULE_CENTRAL_ONLY:
                if report.external_config_violations > 0:
                    findings.append(ConfigFinding(
                        severity=SEVERITY_CRITICAL, code=rule,
                        message=(
                            f"{report.external_config_violations} attempt(s) to keep "
                            "config outside the central engine."
                        ),
                        affected="external_config", category="policy",
                        resolution_hint="Route all configuration through configuration_management.",
                    ))
                    critical_fail = True

            elif rule == RULE_VALIDATED:
                critical_issues = [
                    i for i in report.issues
                    if i.severity == SEVERITY_CRITICAL
                ]
                if critical_issues:
                    findings.append(ConfigFinding(
                        severity=SEVERITY_CRITICAL, code=rule,
                        message=f"{len(critical_issues)} critical validation issue(s).",
                        affected=",".join(i.key for i in critical_issues[:5]),
                        category="validation",
                    ))
                    critical_fail = True
                elif report.issue_count > 0:
                    findings.append(ConfigFinding(
                        severity=SEVERITY_MEDIUM, code=rule,
                        message=f"{report.issue_count} non-critical validation issue(s).",
                        affected="issues", category="validation",
                    ))
                    warnings += 1

            elif rule == RULE_VERSIONED:
                if report.current_version < 1 or not report.versions:
                    findings.append(ConfigFinding(
                        severity=SEVERITY_CRITICAL, code=rule,
                        message="Configuration is not versioned.",
                        affected="versions", category="versioning",
                    ))
                    critical_fail = True

            elif rule == RULE_PROTECTED:
                # sensitive keys must be marked
                unmarked = [
                    e for e in report.entries
                    if any(s in e.key.lower() for s in ("password", "secret", "token", "api_key"))
                    and not e.sensitive
                ]
                if unmarked:
                    findings.append(ConfigFinding(
                        severity=SEVERITY_HIGH, code=rule,
                        message=f"{len(unmarked)} sensitive key(s) not marked protected.",
                        affected=",".join(e.key for e in unmarked[:5]),
                        category="protection",
                    ))
                    warnings += 1

            elif rule == RULE_SELF_VERIFICATION:
                if not report.self_verification_passed:
                    findings.append(ConfigFinding(
                        severity=SEVERITY_CRITICAL, code=rule,
                        message="Self-verification did not pass.",
                        affected="report", category="self_verification",
                    ))
                    critical_fail = True

            elif rule == RULE_QUALITY_PASS:
                if report.entry_count == 0:
                    findings.append(ConfigFinding(
                        severity=SEVERITY_CRITICAL, code=rule,
                        message="No configuration entries registered.",
                        affected="entries", category="quality",
                    ))
                    critical_fail = True
                if not report.synced:
                    findings.append(ConfigFinding(
                        severity=SEVERITY_MEDIUM, code=rule,
                        message="Configuration not fully synchronized across scopes.",
                        affected="sync", category="quality",
                    ))
                    warnings += 1
                if not report.backups:
                    findings.append(ConfigFinding(
                        severity=SEVERITY_MEDIUM, code=rule,
                        message="No configuration backup present.",
                        affected="backups", category="quality",
                    ))
                    warnings += 1

        if critical_fail:
            return findings, False, VERDICT_NOT_READY
        if warnings > 0 or any(f.severity == SEVERITY_HIGH for f in findings):
            return findings, True, VERDICT_READY_WITH_WARNINGS
        return findings, True, VERDICT_READY


__all__ = ["QualityGate"]
