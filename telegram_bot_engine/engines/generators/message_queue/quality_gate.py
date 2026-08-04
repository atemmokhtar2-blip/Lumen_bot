"""QualityGate — Specification 062 (MAXIMUM CRITICAL)"""

from __future__ import annotations

from typing import List, Tuple

from .report_data import (
    MessageQueueReport, QueueFinding,
    SEVERITY_CRITICAL, SEVERITY_HIGH, SEVERITY_MEDIUM,
    RULE_NO_LOSS, RULE_NO_DUPLICATE, RULE_ORDERING, RULE_RETRY_POLICY,
    RULE_SELF_VERIFICATION, RULE_QUALITY_PASS, ALL_QUALITY_RULES,
    VERDICT_READY, VERDICT_READY_WITH_WARNINGS, VERDICT_NOT_READY,
    MSG_DELIVERED, MSG_DEAD, MSG_DUPLICATE,
)


class QualityGate:
    def validate(
        self, report: MessageQueueReport
    ) -> Tuple[List[QueueFinding], bool, str]:
        findings: List[QueueFinding] = []
        critical_fail = False
        warnings = 0

        for rule in ALL_QUALITY_RULES:
            if rule == RULE_NO_LOSS:
                if report.lost_count > 0:
                    findings.append(QueueFinding(
                        severity=SEVERITY_CRITICAL, code=rule,
                        message=f"{report.lost_count} message(s) lost.",
                        affected="messages", category="reliability",
                        resolution_hint="Enable persistence and verify delivery.",
                    ))
                    critical_fail = True

            elif rule == RULE_NO_DUPLICATE:
                # Duplicates detected and marked are OK; unintended re-processing is not
                reprocessed = [
                    m for m in report.messages
                    if m.status == MSG_DELIVERED and m.retry_count == 0
                    and m.dedupe_key and sum(
                        1 for x in report.messages
                        if x.dedupe_key == m.dedupe_key and x.status == MSG_DELIVERED
                    ) > 1
                ]
                if reprocessed:
                    findings.append(QueueFinding(
                        severity=SEVERITY_CRITICAL, code=rule,
                        message="Duplicate messages were processed more than once.",
                        affected="dedupe", category="deduplication",
                    ))
                    critical_fail = True
                elif report.duplicate_count > 0:
                    findings.append(QueueFinding(
                        severity=SEVERITY_MEDIUM, code=rule,
                        message=f"{report.duplicate_count} duplicate(s) detected and skipped.",
                        affected="dedupe", category="deduplication",
                    ))
                    warnings += 1

            elif rule == RULE_ORDERING:
                # Check priority ordering among delivered priority-queue messages
                prio_msgs = [
                    m for m in report.messages
                    if m.queue_kind == "priority" and m.status == MSG_DELIVERED
                ]
                if len(prio_msgs) >= 2:
                    priorities = [m.priority for m in prio_msgs]
                    if priorities != sorted(priorities):
                        findings.append(QueueFinding(
                            severity=SEVERITY_HIGH, code=rule,
                            message="Priority ordering may not be preserved.",
                            affected="priority_queue", category="ordering",
                        ))
                        warnings += 1

            elif rule == RULE_RETRY_POLICY:
                exhausted = [
                    m for m in report.messages
                    if m.status == MSG_DEAD and m.retry_count < m.max_retries
                ]
                if exhausted:
                    findings.append(QueueFinding(
                        severity=SEVERITY_CRITICAL, code=rule,
                        message="Messages moved to DLQ before exhausting retries.",
                        affected="retry", category="retry",
                    ))
                    critical_fail = True
                if report.dlq_count > 0 and report.retry_count == 0:
                    findings.append(QueueFinding(
                        severity=SEVERITY_HIGH, code=rule,
                        message="DLQ entries without any retry attempts.",
                        affected="dlq", category="retry",
                    ))
                    warnings += 1

            elif rule == RULE_SELF_VERIFICATION:
                if not report.self_verification_passed:
                    findings.append(QueueFinding(
                        severity=SEVERITY_CRITICAL, code=rule,
                        message="Self-verification did not pass.",
                        affected="report", category="self_verification",
                    ))
                    critical_fail = True

            elif rule == RULE_QUALITY_PASS:
                if report.message_count == 0:
                    findings.append(QueueFinding(
                        severity=SEVERITY_HIGH, code=rule,
                        message="No messages processed.",
                        affected="messages", category="quality",
                    ))
                    warnings += 1
                if report.delivered_count == 0 and report.dlq_count == 0 and report.message_count > 0:
                    pending_only = all(
                        m.status not in (MSG_DELIVERED, MSG_DEAD)
                        for m in report.messages if m.status != MSG_DUPLICATE
                    )
                    if pending_only:
                        findings.append(QueueFinding(
                            severity=SEVERITY_HIGH, code=rule,
                            message="No messages reached a terminal state.",
                            affected="delivery", category="quality",
                        ))
                        warnings += 1

        if critical_fail:
            return findings, False, VERDICT_NOT_READY
        if warnings > 0 or any(f.severity == SEVERITY_HIGH for f in findings):
            return findings, True, VERDICT_READY_WITH_WARNINGS
        return findings, True, VERDICT_READY


__all__ = ["QualityGate"]
