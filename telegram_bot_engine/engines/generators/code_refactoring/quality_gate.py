"""QualityGate — Specification 038 (ULTRA CRITICAL)"""

from __future__ import annotations

from typing import List, Tuple

from .report_data import (
    CodeRefactoringReport, RefactoringFinding,
    SEVERITY_CRITICAL, SEVERITY_HIGH, SEVERITY_MEDIUM,
    RULE_NO_BEHAVIOR_CHANGE, RULE_ARCHITECTURE_PRESERVED,
    RULE_INTERFACES_PRESERVED, RULE_CONTRACTS_PRESERVED,
    RULE_SELF_VERIFICATION_PASSED, RULE_REGRESSION_SAFE,
    RULE_QUALITY_PASS, RULE_SUFFICIENT_CONFIDENCE,
    ALL_QUALITY_RULES, MIN_MAINTAINABILITY, CONFIDENCE_MEDIUM_THRESHOLD,
    VERDICT_READY, VERDICT_READY_WITH_WARNINGS, VERDICT_NOT_READY,
    STATUS_APPLIED, STATUS_REJECTED,
)


class QualityGate:
    def validate(
        self, report: CodeRefactoringReport
    ) -> Tuple[List[RefactoringFinding], bool, str]:
        findings: List[RefactoringFinding] = []
        critical_fail = False
        warnings = 0

        if report.is_empty and report.unit_count == 0:
            findings.append(RefactoringFinding(
                severity=SEVERITY_MEDIUM, code="empty_report",
                message="Refactoring Report has no units.",
                affected="report", category="quality",
            ))
            warnings += 1

        for rule in ALL_QUALITY_RULES:
            if rule == RULE_NO_BEHAVIOR_CHANGE:
                unsafe = [
                    a for a in report.actions
                    if a.status == STATUS_APPLIED and not a.behavior_safe
                ]
                bad_units = [u for u in report.units if not u.behavior_preserved]
                if unsafe or bad_units:
                    findings.append(RefactoringFinding(
                        severity=SEVERITY_CRITICAL, code=rule,
                        message=(
                            f"{len(unsafe)} unsafe action(s), "
                            f"{len(bad_units)} unit(s) may change behaviour."
                        ),
                        affected="actions/units", category="regression",
                        resolution_hint="Reject behaviour-changing refactorings.",
                    ))
                    critical_fail = True

            elif rule == RULE_ARCHITECTURE_PRESERVED:
                arch_break = [
                    a for a in report.actions
                    if a.status == STATUS_APPLIED and not a.architecture_safe
                ]
                if arch_break:
                    findings.append(RefactoringFinding(
                        severity=SEVERITY_CRITICAL, code=rule,
                        message=f"{len(arch_break)} action(s) may break architecture.",
                        affected="actions", category="architecture",
                    ))
                    critical_fail = True

            elif rule == RULE_INTERFACES_PRESERVED:
                # Covered by architecture_safe flag on actions
                pass

            elif rule == RULE_CONTRACTS_PRESERVED:
                pass

            elif rule == RULE_SELF_VERIFICATION_PASSED:
                if not report.self_verification_passed:
                    findings.append(RefactoringFinding(
                        severity=SEVERITY_CRITICAL, code=rule,
                        message="Self-verification did not pass.",
                        affected="report", category="self_verification",
                    ))
                    critical_fail = True

            elif rule == RULE_REGRESSION_SAFE:
                if not report.regression_safe:
                    findings.append(RefactoringFinding(
                        severity=SEVERITY_CRITICAL, code=rule,
                        message="Regression validation failed.",
                        affected="report", category="regression",
                    ))
                    critical_fail = True

            elif rule == RULE_QUALITY_PASS:
                if (
                    report.unit_count
                    and report.average_maintainability_after < MIN_MAINTAINABILITY
                ):
                    findings.append(RefactoringFinding(
                        severity=SEVERITY_HIGH, code=rule,
                        message=(
                            f"Maintainability {report.average_maintainability_after:.1f} "
                            f"< {MIN_MAINTAINABILITY}."
                        ),
                        affected="units", category="quality",
                    ))
                    warnings += 1
                if report.rejected_count and report.rejected_count == report.action_count:
                    findings.append(RefactoringFinding(
                        severity=SEVERITY_MEDIUM, code=rule,
                        message="All refactoring actions were rejected.",
                        affected="actions", category="quality",
                    ))
                    warnings += 1

            elif rule == RULE_SUFFICIENT_CONFIDENCE:
                conf = report.provenance.confidence if report.provenance else 0.0
                if conf < CONFIDENCE_MEDIUM_THRESHOLD:
                    findings.append(RefactoringFinding(
                        severity=SEVERITY_MEDIUM, code=rule,
                        message=f"Confidence {conf:.2f} below threshold.",
                        affected="provenance", category="confidence",
                    ))
                    warnings += 1

        if critical_fail:
            return findings, False, VERDICT_NOT_READY
        if warnings > 0 or any(f.severity == SEVERITY_HIGH for f in findings):
            return findings, True, VERDICT_READY_WITH_WARNINGS
        return findings, True, VERDICT_READY


__all__ = ["QualityGate"]
