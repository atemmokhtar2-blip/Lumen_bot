"""QualityGate — Specification 028"""

from __future__ import annotations

from typing import List, Tuple

from .report_data import (
    GenerationSessionReport, OrchestratorFinding,
    SEVERITY_CRITICAL, SEVERITY_HIGH, SEVERITY_MEDIUM,
    RULE_SESSION_CREATED, RULE_TASKS_DISTRIBUTED, RULE_NO_CRITICAL_ERRORS,
    RULE_CHECKPOINTS_DEFINED, RULE_READINESS_APPROVED, RULE_SUFFICIENT_CONFIDENCE,
    ALL_QUALITY_RULES, CONFIDENCE_MEDIUM_THRESHOLD,
    VERDICT_READY, VERDICT_READY_WITH_WARNINGS, VERDICT_NOT_READY,
    STATUS_PENDING, STATUS_RUNNING,
)


class QualityGate:
    def validate(self, report: GenerationSessionReport) -> Tuple[List[OrchestratorFinding], bool, str]:
        findings: List[OrchestratorFinding] = []
        critical = False
        warnings = 0

        if report.is_empty:
            findings.append(OrchestratorFinding(
                severity=SEVERITY_CRITICAL, code="empty_report",
                message="Generation Session Report is empty.",
                affected="report", category="quality",
            ))
            return findings, False, VERDICT_NOT_READY

        for rule in ALL_QUALITY_RULES:
            ok = True
            if rule == RULE_SESSION_CREATED:
                if not report.session_id:
                    findings.append(OrchestratorFinding(
                        severity=SEVERITY_CRITICAL, code=rule,
                        message="No session_id assigned.",
                        affected="session", category="session"))
                    ok = False
            elif rule == RULE_TASKS_DISTRIBUTED:
                if not report.tasks:
                    findings.append(OrchestratorFinding(
                        severity=SEVERITY_CRITICAL, code=rule,
                        message="No tasks distributed.",
                        affected="tasks", category="distribution"))
                    ok = False
            elif rule == RULE_NO_CRITICAL_ERRORS:
                failed = [t for t in report.tasks if t.status == "failed"]
                if failed:
                    findings.append(OrchestratorFinding(
                        severity=SEVERITY_CRITICAL, code=rule,
                        message=f"{len(failed)} task(s) already failed at orchestration time.",
                        affected="tasks", category="errors"))
                    ok = False
            elif rule == RULE_CHECKPOINTS_DEFINED:
                if not report.checkpoints:
                    findings.append(OrchestratorFinding(
                        severity=SEVERITY_HIGH, code=rule,
                        message="No checkpoints defined.",
                        affected="checkpoints", category="recovery"))
                    ok = False
            elif rule == RULE_READINESS_APPROVED:
                if not report.readiness_approved:
                    findings.append(OrchestratorFinding(
                        severity=SEVERITY_CRITICAL, code=rule,
                        message=f"Readiness not approved (score={report.readiness_score}).",
                        affected="readiness", category="gate"))
                    ok = False
            elif rule == RULE_SUFFICIENT_CONFIDENCE:
                if report.provenance.confidence < CONFIDENCE_MEDIUM_THRESHOLD:
                    findings.append(OrchestratorFinding(
                        severity=SEVERITY_MEDIUM, code=rule,
                        message=f"Confidence {report.provenance.confidence:.2f} below threshold.",
                        affected="provenance", category="quality"))
                    ok = False

            if not ok:
                if rule in (RULE_SESSION_CREATED, RULE_TASKS_DISTRIBUTED,
                            RULE_NO_CRITICAL_ERRORS, RULE_READINESS_APPROVED):
                    critical = True
                else:
                    warnings += 1

        if critical:
            return findings, False, VERDICT_NOT_READY
        if warnings:
            return findings, True, VERDICT_READY_WITH_WARNINGS
        return findings, True, VERDICT_READY


__all__ = ["QualityGate"]
