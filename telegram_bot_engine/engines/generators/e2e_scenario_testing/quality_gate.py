"""QualityGate — Specification 044 (ULTRA CRITICAL)"""

from __future__ import annotations

from typing import List, Tuple

from .report_data import (
    E2EScenarioTestingReport, E2EFinding,
    SEVERITY_CRITICAL, SEVERITY_HIGH, SEVERITY_MEDIUM,
    RULE_NO_SCENARIO_FAILURE, RULE_LOAD_OK, RULE_RECOVERY_OK, RULE_UX_OK,
    RULE_SELF_VERIFICATION, RULE_QUALITY_PASS, RULE_SUFFICIENT_CONFIDENCE,
    ALL_QUALITY_RULES, MIN_UX_SCORE, MIN_SUCCESS_RATE, CONFIDENCE_MEDIUM_THRESHOLD,
    VERDICT_READY, VERDICT_READY_WITH_WARNINGS, VERDICT_NOT_READY,
    STATUS_FAILED, SCN_LOAD, SCN_RECOVERY,
)


class QualityGate:
    def validate(
        self, report: E2EScenarioTestingReport
    ) -> Tuple[List[E2EFinding], bool, str]:
        findings: List[E2EFinding] = []
        critical_fail = False
        warnings = 0

        if report.is_empty and report.scenario_count == 0:
            findings.append(E2EFinding(
                severity=SEVERITY_CRITICAL, code="empty_report",
                message="No E2E scenarios executed.",
                affected="report", category="e2e",
            ))
            critical_fail = True

        failed = [s for s in report.scenarios if s.status == STATUS_FAILED]

        for rule in ALL_QUALITY_RULES:
            if rule == RULE_NO_SCENARIO_FAILURE:
                if failed or report.failed_count > 0:
                    findings.append(E2EFinding(
                        severity=SEVERITY_CRITICAL, code=rule,
                        message=(
                            f"{len(failed) or report.failed_count} scenario(s) failed."
                        ),
                        affected="scenarios", category="e2e",
                        resolution_hint="Fix failing E2E scenarios before delivery.",
                    ))
                    critical_fail = True
                if report.unexpected_count > 0:
                    findings.append(E2EFinding(
                        severity=SEVERITY_HIGH, code=rule,
                        message=f"{report.unexpected_count} unexpected behavior signal(s).",
                        affected="scenarios", category="behavior",
                    ))
                    warnings += 1

            elif rule == RULE_LOAD_OK:
                bad_load = [
                    l for l in report.load_results if l.status == STATUS_FAILED
                ]
                if bad_load:
                    findings.append(E2EFinding(
                        severity=SEVERITY_CRITICAL, code=rule,
                        message=f"{len(bad_load)} load simulation failure(s).",
                        affected="load", category="load",
                    ))
                    critical_fail = True

            elif rule == RULE_RECOVERY_OK:
                bad_rec = [
                    r for r in report.recoveries
                    if not r.recovered or r.status == STATUS_FAILED
                ]
                if bad_rec:
                    findings.append(E2EFinding(
                        severity=SEVERITY_CRITICAL, code=rule,
                        message=f"{len(bad_rec)} recovery failure(s).",
                        affected="recovery", category="recovery",
                    ))
                    critical_fail = True

            elif rule == RULE_UX_OK:
                overall = report.ux.overall if report.ux else 0.0
                if overall < MIN_UX_SCORE:
                    findings.append(E2EFinding(
                        severity=SEVERITY_HIGH, code=rule,
                        message=f"UX score {overall:.1f} < {MIN_UX_SCORE}.",
                        affected="ux", category="ux",
                    ))
                    warnings += 1

            elif rule == RULE_SELF_VERIFICATION:
                if not report.self_verification_passed:
                    findings.append(E2EFinding(
                        severity=SEVERITY_CRITICAL, code=rule,
                        message="Self-verification did not pass.",
                        affected="report", category="self_verification",
                    ))
                    critical_fail = True

            elif rule == RULE_QUALITY_PASS:
                if report.success_rate < MIN_SUCCESS_RATE:
                    findings.append(E2EFinding(
                        severity=SEVERITY_HIGH, code=rule,
                        message=(
                            f"Success rate {report.success_rate:.1f}% "
                            f"< {MIN_SUCCESS_RATE}%."
                        ),
                        affected="scenarios", category="quality",
                    ))
                    warnings += 1

            elif rule == RULE_SUFFICIENT_CONFIDENCE:
                conf = report.provenance.confidence if report.provenance else 0.0
                if conf < CONFIDENCE_MEDIUM_THRESHOLD:
                    findings.append(E2EFinding(
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
