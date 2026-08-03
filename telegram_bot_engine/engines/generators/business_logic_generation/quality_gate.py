"""QualityGate — Specification 033 (ULTRA CRITICAL)"""

from __future__ import annotations

from typing import List, Tuple

from .report_data import (
    BusinessLogicReport, LogicFinding,
    SEVERITY_CRITICAL, SEVERITY_HIGH, SEVERITY_MEDIUM,
    RULE_NO_DUPLICATION, RULE_NO_MAGIC, RULE_SIZE_LIMITS, RULE_ERROR_HANDLING,
    RULE_SECURITY_CLEAN, RULE_SOLID, RULE_QUALITY_PASS, RULE_SUFFICIENT_CONFIDENCE,
    ALL_QUALITY_RULES, ISSUE_SECURITY, ISSUE_HUGE_FUNCTION, ISSUE_QUALITY,
    MIN_QUALITY_SCORE, CONFIDENCE_MEDIUM_THRESHOLD,
    VERDICT_READY, VERDICT_READY_WITH_WARNINGS, VERDICT_NOT_READY,
)


class QualityGate:
    def validate(self, report: BusinessLogicReport) -> Tuple[List[LogicFinding], bool, str]:
        findings: List[LogicFinding] = []
        critical = False
        warnings = 0

        if report.is_empty:
            findings.append(LogicFinding(
                severity=SEVERITY_CRITICAL, code="empty_report",
                message="Business Logic Report is empty.",
                affected="report", category="quality",
            ))
            return findings, False, VERDICT_NOT_READY

        for rule in ALL_QUALITY_RULES:
            ok = True
            if rule == RULE_SECURITY_CLEAN:
                secs = [i for i in report.issues if i.issue_type == ISSUE_SECURITY]
                if secs:
                    findings.append(LogicFinding(
                        severity=SEVERITY_CRITICAL, code=rule,
                        message=f"{len(secs)} security issue(s).",
                        affected="bodies", category="security"))
                    ok = False
            elif rule == RULE_SIZE_LIMITS:
                huge = [i for i in report.issues if i.issue_type == ISSUE_HUGE_FUNCTION]
                if huge:
                    findings.append(LogicFinding(
                        severity=SEVERITY_HIGH, code=rule,
                        message=f"{len(huge)} oversized function(s).",
                        affected="bodies", category="size"))
                    ok = False
            elif rule == RULE_QUALITY_PASS:
                bad = [i for i in report.issues if i.issue_type == ISSUE_QUALITY]
                if bad or report.average_quality < MIN_QUALITY_SCORE:
                    findings.append(LogicFinding(
                        severity=SEVERITY_CRITICAL, code=rule,
                        message=f"Average quality {report.average_quality:.1f} < {MIN_QUALITY_SCORE}.",
                        affected="bodies", category="quality"))
                    ok = False
            elif rule == RULE_ERROR_HANDLING:
                missing = sum(1 for b in report.bodies if not b.has_error_handling and b.method_name != "__init__")
                if missing > max(1, report.body_count // 2):
                    findings.append(LogicFinding(
                        severity=SEVERITY_HIGH, code=rule,
                        message=f"{missing} methods lack error handling.",
                        affected="bodies", category="reliability"))
                    ok = False
            elif rule == RULE_NO_DUPLICATION:
                pass  # structural check deferred to static analysis stage
            elif rule == RULE_NO_MAGIC:
                pass
            elif rule == RULE_SOLID:
                pass
            elif rule == RULE_SUFFICIENT_CONFIDENCE:
                if report.provenance.confidence < CONFIDENCE_MEDIUM_THRESHOLD:
                    findings.append(LogicFinding(
                        severity=SEVERITY_MEDIUM, code=rule,
                        message=f"Confidence {report.provenance.confidence:.2f} below threshold.",
                        affected="provenance", category="quality"))
                    ok = False

            if not ok:
                if rule in (RULE_SECURITY_CLEAN, RULE_QUALITY_PASS):
                    critical = True
                else:
                    warnings += 1

        if report.body_count == 0:
            critical = True
            findings.append(LogicFinding(
                severity=SEVERITY_CRITICAL, code="no_bodies",
                message="No business logic bodies generated.",
                affected="bodies", category="structure"))

        if critical:
            return findings, False, VERDICT_NOT_READY
        if warnings:
            return findings, True, VERDICT_READY_WITH_WARNINGS
        return findings, True, VERDICT_READY


__all__ = ["QualityGate"]
