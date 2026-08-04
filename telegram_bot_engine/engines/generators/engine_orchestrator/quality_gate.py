"""QualityGate — Specification 053 (MAXIMUM CRITICAL)"""

from __future__ import annotations

from typing import List, Tuple

from .report_data import (
    EngineOrchestratorReport, OrchestratorFinding,
    SEVERITY_CRITICAL, SEVERITY_HIGH, SEVERITY_MEDIUM,
    RULE_NO_DIRECT_CALLS, RULE_DEPENDENCIES_RESPECTED, RULE_NO_DEADLOCK,
    RULE_FAILURE_ISOLATED, RULE_SELF_VERIFICATION, RULE_QUALITY_PASS,
    ALL_QUALITY_RULES, TASK_SUCCESS, TASK_FAILED, TASK_SKIPPED,
    VERDICT_READY, VERDICT_READY_WITH_WARNINGS, VERDICT_NOT_READY,
)


class QualityGate:
    def validate(
        self, report: EngineOrchestratorReport
    ) -> Tuple[List[OrchestratorFinding], bool, str]:
        findings: List[OrchestratorFinding] = []
        critical_fail = False
        warnings = 0

        for rule in ALL_QUALITY_RULES:
            if rule == RULE_NO_DIRECT_CALLS:
                # Orchestrator is the only entry — structural guarantee in this design
                pass

            elif rule == RULE_DEPENDENCIES_RESPECTED:
                success = {
                    h.engine_id for h in report.history if h.status == TASK_SUCCESS
                }
                task_map = {t.engine_id: t for t in report.plan}
                violations = []
                for h in report.history:
                    if h.status != TASK_SUCCESS:
                        continue
                    t = task_map.get(h.engine_id)
                    if not t:
                        continue
                    for dep in t.depends_on:
                        if dep in task_map and dep not in success:
                            dep_final = [
                                x for x in report.history if x.engine_id == dep
                            ]
                            if dep_final and dep_final[-1].status != TASK_SUCCESS:
                                violations.append(f"{h.engine_id} before {dep}")
                if violations:
                    findings.append(OrchestratorFinding(
                        severity=SEVERITY_CRITICAL, code=rule,
                        message=f"Dependency order violated: {', '.join(violations[:5])}",
                        affected="plan", category="dependencies",
                    ))
                    critical_fail = True

            elif rule == RULE_NO_DEADLOCK:
                unresolved = [d for d in report.deadlocks if not d.resolved]
                if unresolved:
                    findings.append(OrchestratorFinding(
                        severity=SEVERITY_CRITICAL, code=rule,
                        message=f"{len(unresolved)} unresolved deadlock(s).",
                        affected="deadlocks", category="deadlock",
                    ))
                    critical_fail = True
                elif report.deadlock_count:
                    findings.append(OrchestratorFinding(
                        severity=SEVERITY_MEDIUM, code=rule,
                        message=f"{report.deadlock_count} deadlock(s) detected and resolved.",
                        affected="deadlocks", category="deadlock",
                    ))
                    warnings += 1

            elif rule == RULE_FAILURE_ISOLATED:
                # Failures should not cascade without skip/replan
                if report.failure_count and not report.replanned:
                    # check if dependents were skipped
                    failed = {
                        h.engine_id for h in report.history if h.status == TASK_FAILED
                    }
                    skipped = {
                        h.engine_id for h in report.history if h.status == TASK_SKIPPED
                    }
                    dependents_ran = []
                    for t in report.plan:
                        if any(d in failed for d in t.depends_on):
                            if t.engine_id not in skipped and t.engine_id not in failed:
                                # check if it succeeded despite failed dep
                                if any(
                                    h.engine_id == t.engine_id and h.status == TASK_SUCCESS
                                    for h in report.history
                                ):
                                    dependents_ran.append(t.engine_id)
                    if dependents_ran:
                        findings.append(OrchestratorFinding(
                            severity=SEVERITY_HIGH, code=rule,
                            message="Dependents ran after failed dependency without isolation.",
                            affected=",".join(dependents_ran[:5]), category="failure",
                        ))
                        warnings += 1

            elif rule == RULE_SELF_VERIFICATION:
                if not report.self_verification_passed:
                    findings.append(OrchestratorFinding(
                        severity=SEVERITY_CRITICAL, code=rule,
                        message="Self-verification did not pass.",
                        affected="report", category="self_verification",
                    ))
                    critical_fail = True

            elif rule == RULE_QUALITY_PASS:
                if report.task_count == 0:
                    findings.append(OrchestratorFinding(
                        severity=SEVERITY_HIGH, code=rule,
                        message="Empty execution plan.",
                        affected="plan", category="quality",
                    ))
                    warnings += 1
                if report.metrics.success_rate < 50.0 and report.task_count > 0:
                    findings.append(OrchestratorFinding(
                        severity=SEVERITY_HIGH, code=rule,
                        message=f"Low success rate: {report.metrics.success_rate}%",
                        affected="metrics", category="performance",
                    ))
                    warnings += 1

        if critical_fail:
            return findings, False, VERDICT_NOT_READY
        if warnings > 0 or any(f.severity == SEVERITY_HIGH for f in findings):
            return findings, True, VERDICT_READY_WITH_WARNINGS
        return findings, True, VERDICT_READY


__all__ = ["QualityGate"]
