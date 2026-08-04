"""QualityGate — Specification 048 (CRITICAL)"""

from __future__ import annotations

from typing import List, Tuple

from .report_data import (
    FileSystemReport, FSFinding,
    SEVERITY_CRITICAL, SEVERITY_HIGH, SEVERITY_MEDIUM,
    RULE_PATH_VALID, RULE_PERMISSION_OK, RULE_BACKUP_BEFORE_MUTATION,
    RULE_INTEGRITY_OK, RULE_WORKSPACE_ISOLATED, RULE_NO_DATA_LOSS,
    RULE_SELF_VERIFICATION, RULE_QUALITY_PASS, ALL_QUALITY_RULES,
    MUTATING_OPS, STATUS_VERIFIED, STATUS_EXECUTED, STATUS_DENIED,
    STATUS_FAILED, STATUS_RECOVERED,
    OP_CREATE_FILE, OP_CREATE_FOLDER, OP_COPY_FILE,
    VERDICT_READY, VERDICT_READY_WITH_WARNINGS, VERDICT_NOT_READY, VERDICT_DENIED,
)


class QualityGate:
    def validate(
        self, report: FileSystemReport
    ) -> Tuple[List[FSFinding], bool, str]:
        findings: List[FSFinding] = []
        critical_fail = False
        warnings = 0

        executed = [
            o for o in report.operations
            if o.status in (STATUS_VERIFIED, STATUS_EXECUTED, STATUS_RECOVERED)
        ]

        for rule in ALL_QUALITY_RULES:
            if rule == RULE_PATH_VALID:
                bad = [p for p in report.path_checks if not p.valid or p.unsafe]
                # Only critical if we still executed against bad paths
                for o in executed:
                    matching_bad = [
                        p for p in bad
                        if p.path in (o.path, o.target_path)
                    ]
                    if matching_bad:
                        findings.append(FSFinding(
                            severity=SEVERITY_CRITICAL, code=rule,
                            message=f"Operation on invalid/unsafe path: {o.path}",
                            affected=o.path, category="path",
                        ))
                        critical_fail = True

            elif rule == RULE_PERMISSION_OK:
                for o in executed:
                    allowed = any(
                        c.operation == o.operation and c.allowed
                        for c in report.permission_checks
                    )
                    if not allowed:
                        findings.append(FSFinding(
                            severity=SEVERITY_CRITICAL, code=rule,
                            message=f"Op {o.operation} without permission.",
                            affected=o.operation, category="permission",
                        ))
                        critical_fail = True

            elif rule == RULE_BACKUP_BEFORE_MUTATION:
                for o in executed:
                    if o.operation in MUTATING_OPS and o.operation not in (
                        OP_CREATE_FILE, OP_CREATE_FOLDER, OP_COPY_FILE,
                    ):
                        if not o.backup_id and o.status != STATUS_RECOVERED:
                            findings.append(FSFinding(
                                severity=SEVERITY_CRITICAL, code=rule,
                                message=f"Mutating op {o.operation} without backup.",
                                affected=o.path, category="backup",
                            ))
                            critical_fail = True

            elif rule == RULE_INTEGRITY_OK:
                bad = [i for i in report.integrity if not i.intact]
                for i in bad:
                    recovered = any(
                        o.recovered and (o.path == i.path or o.target_path == i.path)
                        for o in report.operations
                    )
                    if not recovered:
                        findings.append(FSFinding(
                            severity=SEVERITY_CRITICAL, code=rule,
                            message=f"Integrity failure on {i.path}",
                            affected=i.path, category="integrity",
                        ))
                        critical_fail = True

            elif rule == RULE_WORKSPACE_ISOLATED:
                if not report.workspace_isolated:
                    findings.append(FSFinding(
                        severity=SEVERITY_CRITICAL, code=rule,
                        message="Workspace isolation violated.",
                        affected="workspace", category="isolation",
                    ))
                    critical_fail = True

            elif rule == RULE_NO_DATA_LOSS:
                lost = [
                    o for o in report.operations
                    if o.status == STATUS_FAILED and not o.recovered
                    and o.operation in MUTATING_OPS
                ]
                if lost:
                    findings.append(FSFinding(
                        severity=SEVERITY_CRITICAL, code=rule,
                        message=f"{len(lost)} mutating op(s) failed without recovery.",
                        affected="operations", category="data_loss",
                    ))
                    critical_fail = True

            elif rule == RULE_SELF_VERIFICATION:
                if not report.self_verification_passed:
                    findings.append(FSFinding(
                        severity=SEVERITY_CRITICAL, code=rule,
                        message="Self-verification did not pass.",
                        affected="report", category="self_verification",
                    ))
                    critical_fail = True

            elif rule == RULE_QUALITY_PASS:
                if report.failed_count:
                    findings.append(FSFinding(
                        severity=SEVERITY_HIGH, code=rule,
                        message=f"{report.failed_count} file operation(s) failed.",
                        affected="operations", category="execution",
                    ))
                    warnings += 1
                if report.duplicates:
                    findings.append(FSFinding(
                        severity=SEVERITY_MEDIUM, code=rule,
                        message=f"{len(report.duplicates)} duplicate path signal(s).",
                        affected="duplicates", category="duplicates",
                    ))
                    warnings += 1

        if critical_fail:
            return findings, False, VERDICT_NOT_READY
        if report.denied_count and not executed:
            return findings, True, VERDICT_DENIED
        if warnings > 0 or any(f.severity == SEVERITY_HIGH for f in findings):
            return findings, True, VERDICT_READY_WITH_WARNINGS
        return findings, True, VERDICT_READY


__all__ = ["QualityGate"]
