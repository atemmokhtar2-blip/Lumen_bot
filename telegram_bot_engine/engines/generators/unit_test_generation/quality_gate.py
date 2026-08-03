"""QualityGate — Specification 043 (ULTRA CRITICAL)"""

from __future__ import annotations

from typing import List, Tuple

from .report_data import (
    UnitTestGenerationReport, UnitTestFinding,
    SEVERITY_CRITICAL, SEVERITY_HIGH, SEVERITY_MEDIUM,
    RULE_NO_UNIT_WITHOUT_TEST, RULE_ALL_TESTS_PASS, RULE_COVERAGE_OK,
    RULE_SELF_VERIFICATION, RULE_QUALITY_PASS, RULE_SUFFICIENT_CONFIDENCE,
    ALL_QUALITY_RULES,
    MIN_LINE_COVERAGE, MIN_BRANCH_COVERAGE, MIN_METHOD_COVERAGE,
    MIN_OVERALL_COVERAGE, CONFIDENCE_MEDIUM_THRESHOLD,
    VERDICT_READY, VERDICT_READY_WITH_WARNINGS, VERDICT_NOT_READY,
    STATUS_FAILED, STATUS_GAP,
)


class QualityGate:
    def validate(
        self, report: UnitTestGenerationReport
    ) -> Tuple[List[UnitTestFinding], bool, str]:
        findings: List[UnitTestFinding] = []
        critical_fail = False
        warnings = 0

        if report.is_empty and report.test_count == 0:
            findings.append(UnitTestFinding(
                severity=SEVERITY_CRITICAL, code="empty_report",
                message="No unit tests generated.",
                affected="report", category="coverage",
                resolution_hint="Generate tests for all units.",
            ))
            critical_fail = True

        for rule in ALL_QUALITY_RULES:
            if rule == RULE_NO_UNIT_WITHOUT_TEST:
                unfilled = [g for g in report.gaps if not g.filled]
                if unfilled:
                    findings.append(UnitTestFinding(
                        severity=SEVERITY_CRITICAL, code=rule,
                        message=f"{len(unfilled)} unit(s) without tests.",
                        affected="gaps", category="coverage",
                    ))
                    critical_fail = True

            elif rule == RULE_ALL_TESTS_PASS:
                failed = [t for t in report.tests if t.status == STATUS_FAILED]
                if failed or report.failure_count > 0 or not report.all_tests_passed:
                    findings.append(UnitTestFinding(
                        severity=SEVERITY_CRITICAL, code=rule,
                        message=(
                            f"{len(failed) or report.failure_count} failing test(s)."
                        ),
                        affected="tests", category="execution",
                        resolution_hint="Fix failing unit tests before delivery.",
                    ))
                    critical_fail = True

            elif rule == RULE_COVERAGE_OK:
                cov = report.coverage
                if cov.line_coverage < MIN_LINE_COVERAGE:
                    findings.append(UnitTestFinding(
                        severity=SEVERITY_HIGH, code=rule,
                        message=(
                            f"Line coverage {cov.line_coverage:.1f} "
                            f"< {MIN_LINE_COVERAGE}."
                        ),
                        affected="coverage", category="coverage",
                    ))
                    warnings += 1
                if cov.branch_coverage < MIN_BRANCH_COVERAGE:
                    findings.append(UnitTestFinding(
                        severity=SEVERITY_HIGH, code=rule,
                        message=(
                            f"Branch coverage {cov.branch_coverage:.1f} "
                            f"< {MIN_BRANCH_COVERAGE}."
                        ),
                        affected="coverage", category="coverage",
                    ))
                    warnings += 1
                if cov.method_coverage < MIN_METHOD_COVERAGE:
                    findings.append(UnitTestFinding(
                        severity=SEVERITY_CRITICAL, code=rule,
                        message=(
                            f"Method coverage {cov.method_coverage:.1f} "
                            f"< {MIN_METHOD_COVERAGE}."
                        ),
                        affected="coverage", category="coverage",
                    ))
                    critical_fail = True
                if cov.overall < MIN_OVERALL_COVERAGE:
                    findings.append(UnitTestFinding(
                        severity=SEVERITY_HIGH, code=rule,
                        message=(
                            f"Overall coverage {cov.overall:.1f} "
                            f"< {MIN_OVERALL_COVERAGE}."
                        ),
                        affected="coverage", category="coverage",
                    ))
                    warnings += 1

            elif rule == RULE_SELF_VERIFICATION:
                if not report.self_verification_passed:
                    findings.append(UnitTestFinding(
                        severity=SEVERITY_CRITICAL, code=rule,
                        message="Self-verification did not pass.",
                        affected="report", category="self_verification",
                    ))
                    critical_fail = True

            elif rule == RULE_QUALITY_PASS:
                if report.test_count == 0:
                    findings.append(UnitTestFinding(
                        severity=SEVERITY_CRITICAL, code=rule,
                        message="Zero tests produced.",
                        affected="tests", category="quality",
                    ))
                    critical_fail = True

            elif rule == RULE_SUFFICIENT_CONFIDENCE:
                conf = report.provenance.confidence if report.provenance else 0.0
                if conf < CONFIDENCE_MEDIUM_THRESHOLD:
                    findings.append(UnitTestFinding(
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
