"""QualityGate — Specification 049 (CRITICAL)"""

from __future__ import annotations

from typing import List, Tuple

from .report_data import (
    WorkspaceManagementReport, WorkspaceFinding,
    SEVERITY_CRITICAL, SEVERITY_HIGH, SEVERITY_MEDIUM,
    RULE_NO_CROSS_ACCESS, RULE_ISOLATION_OK, RULE_NO_DATA_LOSS,
    RULE_LIFECYCLE_VALID, RULE_SELF_VERIFICATION, RULE_QUALITY_PASS,
    ALL_QUALITY_RULES, STATUS_FAILED, STATUS_DENIED, STATUS_OK,
    VERDICT_READY, VERDICT_READY_WITH_WARNINGS, VERDICT_NOT_READY, VERDICT_DENIED,
)


class QualityGate:
    def validate(
        self, report: WorkspaceManagementReport
    ) -> Tuple[List[WorkspaceFinding], bool, str]:
        findings: List[WorkspaceFinding] = []
        critical_fail = False
        warnings = 0

        for rule in ALL_QUALITY_RULES:
            if rule == RULE_NO_CROSS_ACCESS or rule == RULE_ISOLATION_OK:
                if not report.isolation_ok:
                    findings.append(WorkspaceFinding(
                        severity=SEVERITY_CRITICAL, code=rule,
                        message="Cross-workspace access or isolation breach detected.",
                        affected="workspaces", category="isolation",
                        resolution_hint="Enforce owner boundaries strictly.",
                    ))
                    critical_fail = True

            elif rule == RULE_NO_DATA_LOSS:
                failed_no_recover = [
                    a for a in report.actions
                    if a.status == STATUS_FAILED and a.action in ("delete", "archive")
                ]
                # failed delete is ok if denied; data loss = failed without recovery path
                if report.failed_count and any(
                    a.action in ("recover",) and a.status == STATUS_FAILED
                    for a in report.actions
                ):
                    findings.append(WorkspaceFinding(
                        severity=SEVERITY_HIGH, code=rule,
                        message="Recovery action failed.",
                        affected="actions", category="recovery",
                    ))
                    warnings += 1

            elif rule == RULE_LIFECYCLE_VALID:
                for a in report.actions:
                    if a.status == STATUS_FAILED and a.action in (
                        "open", "suspend", "resume", "archive", "delete",
                    ):
                        findings.append(WorkspaceFinding(
                            severity=SEVERITY_MEDIUM, code=rule,
                            message=f"Lifecycle transition failed: {a.action} on {a.workspace_id}",
                            affected=a.workspace_id, category="lifecycle",
                        ))
                        warnings += 1

            elif rule == RULE_SELF_VERIFICATION:
                if not report.self_verification_passed:
                    findings.append(WorkspaceFinding(
                        severity=SEVERITY_CRITICAL, code=rule,
                        message="Self-verification did not pass.",
                        affected="report", category="self_verification",
                    ))
                    critical_fail = True

            elif rule == RULE_QUALITY_PASS:
                if report.workspace_count == 0 and report.action_count == 0:
                    findings.append(WorkspaceFinding(
                        severity=SEVERITY_MEDIUM, code=rule,
                        message="No workspaces or actions produced.",
                        affected="report", category="quality",
                    ))
                    warnings += 1
                bad_val = [v for v in report.validations if not v.overall_ok]
                if bad_val:
                    findings.append(WorkspaceFinding(
                        severity=SEVERITY_HIGH, code=rule,
                        message=f"{len(bad_val)} workspace validation failure(s).",
                        affected="validations", category="validation",
                    ))
                    warnings += 1

        if critical_fail:
            return findings, False, VERDICT_NOT_READY
        denied_only = (
            report.action_count > 0
            and all(a.status == STATUS_DENIED for a in report.actions)
        )
        if denied_only:
            return findings, True, VERDICT_DENIED
        if warnings > 0 or any(f.severity == SEVERITY_HIGH for f in findings):
            return findings, True, VERDICT_READY_WITH_WARNINGS
        return findings, True, VERDICT_READY


__all__ = ["QualityGate"]
