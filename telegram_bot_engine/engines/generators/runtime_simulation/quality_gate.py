"""QualityGate — Specification 040 (ULTRA CRITICAL)"""

from __future__ import annotations

from typing import List, Tuple

from .report_data import (
    RuntimeSimulationReport, RuntimeFinding,
    SEVERITY_CRITICAL, SEVERITY_HIGH, SEVERITY_MEDIUM,
    RULE_NO_RUNTIME_ERROR, RULE_NO_CRASH, RULE_NO_FAILURE, RULE_NO_MEMORY_LEAK,
    RULE_STARTUP_OK, RULE_SELF_VERIFICATION, RULE_QUALITY_PASS,
    RULE_SUFFICIENT_CONFIDENCE, ALL_QUALITY_RULES,
    MIN_RUNTIME_SCORE, CONFIDENCE_MEDIUM_THRESHOLD,
    VERDICT_READY, VERDICT_READY_WITH_WARNINGS, VERDICT_NOT_READY,
    STATUS_FAILED, EVT_CRASH, EVT_EXCEPTION,
)


class QualityGate:
    def validate(
        self, report: RuntimeSimulationReport
    ) -> Tuple[List[RuntimeFinding], bool, str]:
        findings: List[RuntimeFinding] = []
        critical_fail = False
        warnings = 0

        if report.is_empty and report.event_count == 0:
            findings.append(RuntimeFinding(
                severity=SEVERITY_MEDIUM, code="empty_report",
                message="Runtime Simulation Report has no events.",
                affected="report", category="quality",
            ))
            warnings += 1

        for rule in ALL_QUALITY_RULES:
            if rule == RULE_NO_RUNTIME_ERROR:
                failed = [e for e in report.events if e.status == STATUS_FAILED]
                if failed:
                    # only block on critical-severity failures
                    crit_failed = [
                        e for e in failed
                        if e.severity == SEVERITY_CRITICAL
                    ]
                    if crit_failed:
                        findings.append(RuntimeFinding(
                            severity=SEVERITY_CRITICAL, code=rule,
                            message=f"{len(crit_failed)} critical runtime failure(s).",
                            affected="events", category="runtime",
                            resolution_hint="Fix runtime failures before delivery.",
                        ))
                        critical_fail = True
                    elif len(failed) > 3:
                        findings.append(RuntimeFinding(
                            severity=SEVERITY_HIGH, code=rule,
                            message=f"{len(failed)} runtime failure event(s).",
                            affected="events", category="runtime",
                        ))
                        warnings += 1

            elif rule == RULE_NO_CRASH:
                crashes = [
                    e for e in report.events
                    if e.event_type in (EVT_CRASH, EVT_EXCEPTION)
                    and e.status == STATUS_FAILED
                ]
                if crashes or report.crash_count > 0:
                    findings.append(RuntimeFinding(
                        severity=SEVERITY_CRITICAL, code=rule,
                        message=f"{len(crashes) or report.crash_count} crash/exception event(s).",
                        affected="runtime", category="crash",
                    ))
                    critical_fail = True

            elif rule == RULE_NO_FAILURE:
                hard = [
                    f for f in report.failures
                    if f.status == STATUS_FAILED and not f.recovered
                ]
                if hard:
                    findings.append(RuntimeFinding(
                        severity=SEVERITY_CRITICAL, code=rule,
                        message=f"{len(hard)} unrecovered failure scenario(s).",
                        affected="failures", category="failure",
                    ))
                    critical_fail = True

            elif rule == RULE_NO_MEMORY_LEAK:
                if report.leak_detected:
                    findings.append(RuntimeFinding(
                        severity=SEVERITY_CRITICAL, code=rule,
                        message="Memory leak detected during simulation.",
                        affected="resources", category="memory",
                    ))
                    critical_fail = True

            elif rule == RULE_STARTUP_OK:
                if not report.startup_ok:
                    findings.append(RuntimeFinding(
                        severity=SEVERITY_CRITICAL, code=rule,
                        message="Startup simulation did not succeed.",
                        affected="startup", category="startup",
                    ))
                    critical_fail = True

            elif rule == RULE_SELF_VERIFICATION:
                if not report.self_verification_passed:
                    findings.append(RuntimeFinding(
                        severity=SEVERITY_CRITICAL, code=rule,
                        message="Self-verification did not pass.",
                        affected="report", category="self_verification",
                    ))
                    critical_fail = True

            elif rule == RULE_QUALITY_PASS:
                overall = report.score.overall if report.score else 0.0
                if overall < MIN_RUNTIME_SCORE:
                    findings.append(RuntimeFinding(
                        severity=SEVERITY_HIGH, code=rule,
                        message=f"Runtime score {overall:.1f} < {MIN_RUNTIME_SCORE}.",
                        affected="score", category="quality",
                    ))
                    warnings += 1

            elif rule == RULE_SUFFICIENT_CONFIDENCE:
                conf = report.provenance.confidence if report.provenance else 0.0
                if conf < CONFIDENCE_MEDIUM_THRESHOLD:
                    findings.append(RuntimeFinding(
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
