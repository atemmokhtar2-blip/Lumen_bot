"""QualityGate — Specification 063 (MAXIMUM CRITICAL)"""

from __future__ import annotations

from typing import List, Tuple

from .report_data import (
    TaskSchedulerReport, SchedulerFinding,
    SEVERITY_CRITICAL, SEVERITY_HIGH, SEVERITY_MEDIUM,
    RULE_NO_EARLY_START, RULE_DEPENDENCIES, RULE_LOAD_AWARE,
    RULE_SELF_VERIFICATION, RULE_QUALITY_PASS, ALL_QUALITY_RULES,
    VERDICT_READY, VERDICT_READY_WITH_WARNINGS, VERDICT_NOT_READY,
    STATE_COMPLETED, STATE_RUNNING,
)


class QualityGate:
    def validate(
        self, report: TaskSchedulerReport
    ) -> Tuple[List[SchedulerFinding], bool, str]:
        findings: List[SchedulerFinding] = []
        critical_fail = False
        warnings = 0

        for rule in ALL_QUALITY_RULES:
            if rule == RULE_NO_EARLY_START:
                if report.early_start_violations > 0:
                    findings.append(SchedulerFinding(
                        severity=SEVERITY_CRITICAL, code=rule,
                        message=(
                            f"{report.early_start_violations} task(s) attempted "
                            "start before schedule/window."
                        ),
                        affected="schedule", category="timing",
                        resolution_hint="Respect delay_until and execution windows.",
                    ))
                    critical_fail = True

            elif rule == RULE_DEPENDENCIES:
                if report.dependency_violations > 0:
                    findings.append(SchedulerFinding(
                        severity=SEVERITY_CRITICAL, code=rule,
                        message=(
                            f"{report.dependency_violations} dependency "
                            "violation(s)."
                        ),
                        affected="dependencies", category="dependencies",
                    ))
                    critical_fail = True

            elif rule == RULE_LOAD_AWARE:
                if report.load_throttled > 0:
                    findings.append(SchedulerFinding(
                        severity=SEVERITY_MEDIUM, code=rule,
                        message=(
                            f"{report.load_throttled} task(s) throttled due to load."
                        ),
                        affected="capacity", category="load",
                    ))
                    warnings += 1

            elif rule == RULE_SELF_VERIFICATION:
                if not report.self_verification_passed:
                    findings.append(SchedulerFinding(
                        severity=SEVERITY_CRITICAL, code=rule,
                        message="Self-verification did not pass.",
                        affected="report", category="self_verification",
                    ))
                    critical_fail = True

            elif rule == RULE_QUALITY_PASS:
                if report.task_count == 0:
                    findings.append(SchedulerFinding(
                        severity=SEVERITY_HIGH, code=rule,
                        message="No tasks registered.",
                        affected="tasks", category="quality",
                    ))
                    warnings += 1
                still_running = [
                    t for t in report.tasks if t.state == STATE_RUNNING
                ]
                if still_running:
                    findings.append(SchedulerFinding(
                        severity=SEVERITY_HIGH, code=rule,
                        message=f"{len(still_running)} task(s) still running at end of cycle.",
                        affected=",".join(t.task_id for t in still_running[:5]),
                        category="quality",
                    ))
                    warnings += 1
                if not report.events:
                    findings.append(SchedulerFinding(
                        severity=SEVERITY_HIGH, code=rule,
                        message="Schedule event log is empty.",
                        affected="events", category="quality",
                    ))
                    warnings += 1

        if critical_fail:
            return findings, False, VERDICT_NOT_READY
        if warnings > 0 or any(f.severity == SEVERITY_HIGH for f in findings):
            return findings, True, VERDICT_READY_WITH_WARNINGS
        return findings, True, VERDICT_READY


__all__ = ["QualityGate"]
