"""QualityGate — Specification 046 (CRITICAL)"""

from __future__ import annotations

from typing import List, Tuple

from .report_data import (
    RepositoryManagementReport, RepoFinding,
    SEVERITY_CRITICAL, SEVERITY_HIGH, SEVERITY_MEDIUM,
    RULE_OWNERSHIP_VERIFIED, RULE_PERMISSION_SUFFICIENT,
    RULE_NO_AUTONOMOUS_ACTION, RULE_PLAN_BEFORE_MUTATION,
    RULE_SELF_VERIFICATION, RULE_QUALITY_PASS, ALL_QUALITY_RULES,
    STATUS_EXECUTED, STATUS_DENIED, STATUS_FAILED,
    VERDICT_READY, VERDICT_READY_WITH_WARNINGS, VERDICT_NOT_READY, VERDICT_DENIED,
)


class QualityGate:
    def validate(
        self, report: RepositoryManagementReport
    ) -> Tuple[List[RepoFinding], bool, str]:
        findings: List[RepoFinding] = []
        critical_fail = False
        warnings = 0
        denied_ops = [r for r in report.results if r.status == STATUS_DENIED]

        for rule in ALL_QUALITY_RULES:
            if rule == RULE_OWNERSHIP_VERIFIED:
                executed = [r for r in report.results if r.status == STATUS_EXECUTED]
                if executed and not report.ownership_verified:
                    findings.append(RepoFinding(
                        severity=SEVERITY_CRITICAL, code=rule,
                        message="Executed operations without ownership verification.",
                        affected="operations", category="ownership",
                        resolution_hint="Verify ownership before any repo access.",
                    ))
                    critical_fail = True

            elif rule == RULE_PERMISSION_SUFFICIENT:
                # Executed ops must have matching allowed permission checks
                for r in report.results:
                    if r.status != STATUS_EXECUTED:
                        continue
                    allowed = any(
                        c.operation == r.operation and c.allowed
                        for c in report.permission_checks
                    )
                    if not allowed:
                        findings.append(RepoFinding(
                            severity=SEVERITY_CRITICAL, code=rule,
                            message=f"Operation {r.operation} executed without permission.",
                            affected=r.operation, category="permission",
                        ))
                        critical_fail = True

            elif rule == RULE_NO_AUTONOMOUS_ACTION:
                # Engine must not invent operations beyond user request;
                # empty results with no plans is OK (idle).
                pass

            elif rule == RULE_PLAN_BEFORE_MUTATION:
                mutating_ops = {
                    "commit", "push", "create_branch", "delete_branch",
                    "merge_branch", "create_repository", "rename_repository",
                    "archive_repository",
                }
                for r in report.results:
                    if r.status == STATUS_EXECUTED and r.operation in mutating_ops:
                        has_plan = any(
                            p.plan_id == r.plan_id and p.mutating
                            for p in report.plans
                        ) or any(
                            p.operation == r.operation and p.mutating
                            for p in report.plans
                        )
                        if not has_plan:
                            findings.append(RepoFinding(
                                severity=SEVERITY_CRITICAL, code=rule,
                                message=f"Mutating op {r.operation} without plan.",
                                affected=r.operation, category="safety",
                            ))
                            critical_fail = True

            elif rule == RULE_SELF_VERIFICATION:
                if not report.self_verification_passed:
                    findings.append(RepoFinding(
                        severity=SEVERITY_CRITICAL, code=rule,
                        message="Self-verification did not pass.",
                        affected="report", category="self_verification",
                    ))
                    critical_fail = True

            elif rule == RULE_QUALITY_PASS:
                failed = [r for r in report.results if r.status == STATUS_FAILED]
                if failed:
                    findings.append(RepoFinding(
                        severity=SEVERITY_HIGH, code=rule,
                        message=f"{len(failed)} operation(s) failed.",
                        affected="results", category="execution",
                    ))
                    warnings += 1

        if critical_fail:
            return findings, False, VERDICT_NOT_READY
        if denied_ops and not any(r.status == STATUS_EXECUTED for r in report.results):
            # All denied is a valid secure outcome
            return findings, True, VERDICT_DENIED
        if warnings > 0 or any(f.severity == SEVERITY_HIGH for f in findings):
            return findings, True, VERDICT_READY_WITH_WARNINGS
        return findings, True, VERDICT_READY


__all__ = ["QualityGate"]
