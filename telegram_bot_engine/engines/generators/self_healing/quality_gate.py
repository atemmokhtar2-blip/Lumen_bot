"""QualityGate — Specification 041 (ULTRA CRITICAL)"""

from __future__ import annotations

from typing import List, Tuple

from .report_data import (
    SelfHealingReport, HealingFinding,
    SEVERITY_CRITICAL, SEVERITY_HIGH, SEVERITY_MEDIUM,
    RULE_NO_ARCH_BREAK, RULE_NO_LOGIC_BREAK, RULE_NO_PERF_REGRESSION,
    RULE_NO_SEC_REGRESSION, RULE_ALL_TESTS_PASS, RULE_CONFIDENCE_OK,
    RULE_LIMITS_RESPECTED, RULE_SELF_OK, ALL_QUALITY_RULES,
    MIN_REPAIR_CONFIDENCE, MAX_ATTEMPTS_PER_ISSUE, CONFIDENCE_MEDIUM_THRESHOLD,
    VERDICT_READY, VERDICT_READY_WITH_WARNINGS, VERDICT_NOT_READY,
    STATUS_FAILED, STATUS_HEALED,
)


class QualityGate:
    def validate(
        self, report: SelfHealingReport
    ) -> Tuple[List[HealingFinding], bool, str]:
        findings: List[HealingFinding] = []
        critical_fail = False
        warnings = 0

        if report.is_empty and report.issue_count == 0:
            # No issues is success
            return findings, True, VERDICT_READY

        for rule in ALL_QUALITY_RULES:
            if rule == RULE_NO_ARCH_BREAK:
                bad = [
                    p for p in report.plans
                    if not p.architecture_safe
                ]
                applied_bad = [
                    a for a in report.attempts
                    if a.success and any(
                        p.plan_id == a.plan_id and not p.architecture_safe
                        for p in report.plans
                    )
                ]
                if applied_bad:
                    findings.append(HealingFinding(
                        severity=SEVERITY_CRITICAL, code=rule,
                        message="Repair would break architecture.",
                        affected="plans", category="architecture",
                    ))
                    critical_fail = True

            elif rule == RULE_NO_LOGIC_BREAK:
                bad = [
                    a for a in report.attempts
                    if a.success and any(
                        p.plan_id == a.plan_id and not p.logic_safe
                        for p in report.plans
                    )
                ]
                if bad:
                    findings.append(HealingFinding(
                        severity=SEVERITY_CRITICAL, code=rule,
                        message="Repair would break business logic.",
                        affected="attempts", category="logic",
                    ))
                    critical_fail = True

            elif rule == RULE_NO_PERF_REGRESSION:
                bad = [
                    a for a in report.attempts
                    if a.success and any(
                        p.plan_id == a.plan_id and not p.performance_safe
                        for p in report.plans
                    )
                ]
                if bad:
                    findings.append(HealingFinding(
                        severity=SEVERITY_HIGH, code=rule,
                        message="Repair may regress performance.",
                        affected="attempts", category="performance",
                    ))
                    warnings += 1

            elif rule == RULE_NO_SEC_REGRESSION:
                bad = [
                    a for a in report.attempts
                    if a.success and any(
                        p.plan_id == a.plan_id and not p.security_safe
                        for p in report.plans
                    )
                ]
                if bad:
                    findings.append(HealingFinding(
                        severity=SEVERITY_CRITICAL, code=rule,
                        message="Repair may regress security.",
                        affected="attempts", category="security",
                    ))
                    critical_fail = True

            elif rule == RULE_ALL_TESTS_PASS:
                if not report.all_validations_passed:
                    findings.append(HealingFinding(
                        severity=SEVERITY_CRITICAL, code=rule,
                        message="Validation cycle did not fully pass.",
                        affected="validation", category="validation",
                    ))
                    critical_fail = True
                failed_crit = [
                    i for i in report.issues
                    if i.status == STATUS_FAILED and i.severity == SEVERITY_CRITICAL
                ]
                if failed_crit:
                    findings.append(HealingFinding(
                        severity=SEVERITY_CRITICAL, code=rule,
                        message=f"{len(failed_crit)} critical issue(s) remain unhealed.",
                        affected="issues", category="healing",
                    ))
                    critical_fail = True

            elif rule == RULE_CONFIDENCE_OK:
                low = [
                    p for p in report.plans
                    if p.confidence < MIN_REPAIR_CONFIDENCE
                ]
                # Only warn if we relied on low-confidence plans that were marked success
                if report.average_confidence and report.average_confidence < MIN_REPAIR_CONFIDENCE:
                    findings.append(HealingFinding(
                        severity=SEVERITY_HIGH, code=rule,
                        message=f"Average repair confidence {report.average_confidence:.2f} low.",
                        affected="plans", category="confidence",
                    ))
                    warnings += 1

            elif rule == RULE_LIMITS_RESPECTED:
                over = [
                    i for i in report.issues
                    if i.attempts > MAX_ATTEMPTS_PER_ISSUE
                ]
                if over:
                    findings.append(HealingFinding(
                        severity=SEVERITY_MEDIUM, code=rule,
                        message=f"{len(over)} issue(s) exceeded attempt limits.",
                        affected="issues", category="limits",
                    ))
                    warnings += 1

            elif rule == RULE_SELF_OK:
                if not report.self_verification_passed:
                    findings.append(HealingFinding(
                        severity=SEVERITY_CRITICAL, code=rule,
                        message="Self-verification did not pass.",
                        affected="report", category="self_verification",
                    ))
                    critical_fail = True

        if critical_fail:
            return findings, False, VERDICT_NOT_READY
        if warnings > 0 or any(f.severity == SEVERITY_HIGH for f in findings):
            return findings, True, VERDICT_READY_WITH_WARNINGS
        return findings, True, VERDICT_READY


__all__ = ["QualityGate"]
