"""QualityGate — Specification 064 (MAXIMUM CRITICAL)"""

from __future__ import annotations

from typing import List, Tuple

from .report_data import (
    WorkflowExecutionReport, WorkflowFinding,
    SEVERITY_CRITICAL, SEVERITY_HIGH, SEVERITY_MEDIUM,
    RULE_SEQUENTIAL_GATE, RULE_CHECKPOINTS, RULE_VALIDATED,
    RULE_SELF_VERIFICATION, RULE_QUALITY_PASS, ALL_QUALITY_RULES,
    VERDICT_READY, VERDICT_READY_WITH_WARNINGS, VERDICT_NOT_READY,
    STAGE_COMPLETED, STAGE_RUNNING,
)


class QualityGate:
    def validate(
        self, report: WorkflowExecutionReport
    ) -> Tuple[List[WorkflowFinding], bool, str]:
        findings: List[WorkflowFinding] = []
        critical_fail = False
        warnings = 0

        for rule in ALL_QUALITY_RULES:
            if rule == RULE_SEQUENTIAL_GATE:
                if report.sequential_gate_violations > 0:
                    findings.append(WorkflowFinding(
                        severity=SEVERITY_CRITICAL, code=rule,
                        message=(
                            f"{report.sequential_gate_violations} sequential gate "
                            "violation(s) — stage advanced without prior success."
                        ),
                        affected="stages", category="execution",
                        resolution_hint="Wait for sequential predecessors to complete.",
                    ))
                    critical_fail = True

            elif rule == RULE_CHECKPOINTS:
                completed = [
                    s for s in report.stages if s.state == STAGE_COMPLETED
                ]
                if completed and not report.checkpoints:
                    findings.append(WorkflowFinding(
                        severity=SEVERITY_CRITICAL, code=rule,
                        message="Completed stages without checkpoints.",
                        affected="checkpoints", category="checkpoints",
                    ))
                    critical_fail = True
                elif completed and len(report.checkpoints) < len(completed):
                    findings.append(WorkflowFinding(
                        severity=SEVERITY_MEDIUM, code=rule,
                        message="Fewer checkpoints than completed stages.",
                        affected="checkpoints", category="checkpoints",
                    ))
                    warnings += 1

            elif rule == RULE_VALIDATED:
                unvalidated = [s for s in report.stages if not s.validated]
                if unvalidated:
                    findings.append(WorkflowFinding(
                        severity=SEVERITY_HIGH, code=rule,
                        message=f"{len(unvalidated)} stage(s) not validated.",
                        affected=",".join(s.stage_id for s in unvalidated[:5]),
                        category="validation",
                    ))
                    warnings += 1

            elif rule == RULE_SELF_VERIFICATION:
                if not report.self_verification_passed:
                    findings.append(WorkflowFinding(
                        severity=SEVERITY_CRITICAL, code=rule,
                        message="Self-verification did not pass.",
                        affected="report", category="self_verification",
                    ))
                    critical_fail = True

            elif rule == RULE_QUALITY_PASS:
                if report.stage_count == 0:
                    findings.append(WorkflowFinding(
                        severity=SEVERITY_CRITICAL, code=rule,
                        message="No workflow stages built.",
                        affected="stages", category="quality",
                    ))
                    critical_fail = True
                still_running = [
                    s for s in report.stages if s.state == STAGE_RUNNING
                ]
                if still_running:
                    findings.append(WorkflowFinding(
                        severity=SEVERITY_HIGH, code=rule,
                        message=f"{len(still_running)} stage(s) still running.",
                        affected=",".join(s.stage_id for s in still_running[:5]),
                        category="quality",
                    ))
                    warnings += 1
                if not report.events:
                    findings.append(WorkflowFinding(
                        severity=SEVERITY_HIGH, code=rule,
                        message="Workflow event log is empty.",
                        affected="events", category="quality",
                    ))
                    warnings += 1

        if critical_fail:
            return findings, False, VERDICT_NOT_READY
        if warnings > 0 or any(f.severity == SEVERITY_HIGH for f in findings):
            return findings, True, VERDICT_READY_WITH_WARNINGS
        return findings, True, VERDICT_READY


__all__ = ["QualityGate"]
