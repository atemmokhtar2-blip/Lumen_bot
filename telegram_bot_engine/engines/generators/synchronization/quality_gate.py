"""QualityGate — Specification 055 (CRITICAL)"""

from __future__ import annotations

from typing import List, Tuple

from .report_data import (
    SynchronizationReport, SyncFinding,
    SEVERITY_CRITICAL, SEVERITY_HIGH, SEVERITY_MEDIUM,
    RULE_SINGLE_STATE, RULE_NO_LOST_UPDATES, RULE_CONFLICTS_RESOLVED,
    RULE_ATOMIC_OK, RULE_CONSISTENT, RULE_SELF_VERIFICATION, RULE_QUALITY_PASS,
    ALL_QUALITY_RULES, TX_ABORTED, TX_PENDING,
    VERDICT_READY, VERDICT_READY_WITH_WARNINGS, VERDICT_NOT_READY,
)


class QualityGate:
    def validate(
        self, report: SynchronizationReport
    ) -> Tuple[List[SyncFinding], bool, str]:
        findings: List[SyncFinding] = []
        critical_fail = False
        warnings = 0

        for rule in ALL_QUALITY_RULES:
            if rule == RULE_SINGLE_STATE:
                if not report.consistent:
                    findings.append(SyncFinding(
                        severity=SEVERITY_CRITICAL, code=rule,
                        message="Inconsistent state across engines for the same project.",
                        affected="state", category="consistency",
                        resolution_hint="Force full resync from canonical context version.",
                    ))
                    critical_fail = True

            elif rule == RULE_NO_LOST_UPDATES:
                lost = [c for c in report.conflicts if c.data_lost]
                unapplied = [e for e in report.events if not e.applied]
                if lost:
                    findings.append(SyncFinding(
                        severity=SEVERITY_CRITICAL, code=rule,
                        message=f"{len(lost)} conflict resolution(s) lost data.",
                        affected="conflicts", category="data_loss",
                    ))
                    critical_fail = True
                if unapplied and not report.recovered:
                    findings.append(SyncFinding(
                        severity=SEVERITY_HIGH, code=rule,
                        message=f"{len(unapplied)} update(s) not applied.",
                        affected="events", category="data_loss",
                    ))
                    warnings += 1

            elif rule == RULE_CONFLICTS_RESOLVED:
                if report.unresolved_count > 0:
                    findings.append(SyncFinding(
                        severity=SEVERITY_CRITICAL, code=rule,
                        message=f"{report.unresolved_count} unresolved conflict(s).",
                        affected="conflicts", category="conflict",
                    ))
                    critical_fail = True

            elif rule == RULE_ATOMIC_OK:
                pending = [t for t in report.transactions if t.status == TX_PENDING]
                aborted = [t for t in report.transactions if t.status == TX_ABORTED]
                if pending:
                    findings.append(SyncFinding(
                        severity=SEVERITY_CRITICAL, code=rule,
                        message=f"{len(pending)} transaction(s) still pending.",
                        affected="transactions", category="atomic",
                    ))
                    critical_fail = True
                if aborted and not report.recovered:
                    findings.append(SyncFinding(
                        severity=SEVERITY_HIGH, code=rule,
                        message=f"{len(aborted)} aborted transaction(s) without recovery.",
                        affected="transactions", category="atomic",
                    ))
                    warnings += 1

            elif rule == RULE_CONSISTENT:
                if report.health.consistency_rate < 95.0:
                    findings.append(SyncFinding(
                        severity=SEVERITY_HIGH, code=rule,
                        message=f"Consistency rate low: {report.health.consistency_rate}%",
                        affected="health", category="consistency",
                    ))
                    warnings += 1

            elif rule == RULE_SELF_VERIFICATION:
                if not report.self_verification_passed:
                    findings.append(SyncFinding(
                        severity=SEVERITY_CRITICAL, code=rule,
                        message="Self-verification did not pass.",
                        affected="report", category="self_verification",
                    ))
                    critical_fail = True

            elif rule == RULE_QUALITY_PASS:
                if report.health.conflict_rate > 30.0:
                    findings.append(SyncFinding(
                        severity=SEVERITY_MEDIUM, code=rule,
                        message=f"High conflict rate: {report.health.conflict_rate}%",
                        affected="health", category="quality",
                    ))
                    warnings += 1

        if critical_fail:
            return findings, False, VERDICT_NOT_READY
        if warnings > 0 or any(f.severity == SEVERITY_HIGH for f in findings):
            return findings, True, VERDICT_READY_WITH_WARNINGS
        return findings, True, VERDICT_READY


__all__ = ["QualityGate"]
