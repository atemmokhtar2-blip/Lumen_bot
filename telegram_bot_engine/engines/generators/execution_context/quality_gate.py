"""QualityGate — Specification 054 (CRITICAL)"""

from __future__ import annotations

from typing import List, Tuple

from .report_data import (
    ExecutionContextReport, ContextFinding,
    SEVERITY_CRITICAL, SEVERITY_HIGH, SEVERITY_MEDIUM,
    RULE_SINGLE_ACTIVE, RULE_NO_OUTSIDE_CONTEXT, RULE_ISOLATION_OK,
    RULE_VALID_DATA, RULE_SELF_VERIFICATION, RULE_QUALITY_PASS,
    ALL_QUALITY_RULES,
    VERDICT_READY, VERDICT_READY_WITH_WARNINGS, VERDICT_NOT_READY,
)


class QualityGate:
    def validate(
        self, report: ExecutionContextReport
    ) -> Tuple[List[ContextFinding], bool, str]:
        findings: List[ContextFinding] = []
        critical_fail = False
        warnings = 0

        for rule in ALL_QUALITY_RULES:
            if rule == RULE_SINGLE_ACTIVE:
                if report.active_count != 1:
                    findings.append(ContextFinding(
                        severity=SEVERITY_CRITICAL, code=rule,
                        message=f"Expected 1 active context, found {report.active_count}.",
                        affected="context", category="lifecycle",
                        resolution_hint="Close extra contexts; keep single active per project.",
                    ))
                    critical_fail = True

            elif rule == RULE_NO_OUTSIDE_CONTEXT:
                if not report.context_id:
                    findings.append(ContextFinding(
                        severity=SEVERITY_CRITICAL, code=rule,
                        message="No execution context established.",
                        affected="context", category="lifecycle",
                    ))
                    critical_fail = True

            elif rule == RULE_ISOLATION_OK:
                if not report.isolated:
                    findings.append(ContextFinding(
                        severity=SEVERITY_CRITICAL, code=rule,
                        message="Context isolation failed — cross-project access risk.",
                        affected="project_id", category="isolation",
                    ))
                    critical_fail = True

            elif rule == RULE_VALID_DATA:
                critical_issues = [
                    i for i in report.validation_issues
                    if i.severity == SEVERITY_CRITICAL
                ]
                high_issues = [
                    i for i in report.validation_issues
                    if i.severity == SEVERITY_HIGH
                ]
                if critical_issues:
                    findings.append(ContextFinding(
                        severity=SEVERITY_CRITICAL, code=rule,
                        message=f"{len(critical_issues)} critical context validation issue(s).",
                        affected="validation", category="validation",
                    ))
                    critical_fail = True
                if high_issues:
                    findings.append(ContextFinding(
                        severity=SEVERITY_HIGH, code=rule,
                        message=f"{len(high_issues)} high context validation issue(s).",
                        affected="validation", category="validation",
                    ))
                    warnings += 1

            elif rule == RULE_SELF_VERIFICATION:
                if not report.self_verification_passed:
                    findings.append(ContextFinding(
                        severity=SEVERITY_CRITICAL, code=rule,
                        message="Self-verification did not pass.",
                        affected="report", category="self_verification",
                    ))
                    critical_fail = True

            elif rule == RULE_QUALITY_PASS:
                if not report.shared_keys:
                    findings.append(ContextFinding(
                        severity=SEVERITY_HIGH, code=rule,
                        message="Context has no shared keys.",
                        affected="shared_keys", category="quality",
                    ))
                    warnings += 1
                if report.version < 1:
                    findings.append(ContextFinding(
                        severity=SEVERITY_MEDIUM, code=rule,
                        message="Invalid context version.",
                        affected="version", category="quality",
                    ))
                    warnings += 1

        if critical_fail:
            return findings, False, VERDICT_NOT_READY
        if warnings > 0 or any(f.severity == SEVERITY_HIGH for f in findings):
            return findings, True, VERDICT_READY_WITH_WARNINGS
        return findings, True, VERDICT_READY


__all__ = ["QualityGate"]
