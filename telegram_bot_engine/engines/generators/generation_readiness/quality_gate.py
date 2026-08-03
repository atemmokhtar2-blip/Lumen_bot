"""QualityGate — Specification 027 (requires 100% readiness)."""

from __future__ import annotations

from typing import List, Tuple

from .report_data import (
    GenerationReadinessReport, ReadinessFinding,
    SEVERITY_CRITICAL, SEVERITY_HIGH, SEVERITY_MEDIUM,
    RULE_ALL_BLUEPRINTS_PRESENT, RULE_ALL_VERDICTS_READY, RULE_NO_CRITICAL_ISSUES,
    RULE_SCORE_100, RULE_CONSISTENCY, RULE_SUFFICIENT_CONFIDENCE,
    ALL_QUALITY_RULES, ISSUE_MISSING_BLUEPRINT, ISSUE_NOT_READY_VERDICT,
    ISSUE_INCONSISTENCY, REQUIRED_READINESS, CONFIDENCE_MEDIUM_THRESHOLD,
    VERDICT_READY, VERDICT_READY_WITH_WARNINGS, VERDICT_NOT_READY,
    APPROVAL_APPROVED, APPROVAL_REJECTED,
)


class QualityGate:
    def validate(self, report: GenerationReadinessReport) -> Tuple[List[ReadinessFinding], bool, str, str]:
        """Returns findings, passed, verdict, approval_status."""
        findings: List[ReadinessFinding] = []
        critical = False
        warnings = 0

        if report.is_empty:
            findings.append(ReadinessFinding(
                severity=SEVERITY_CRITICAL, code="empty_report",
                message="Generation Readiness Report is empty.",
                affected="report", category="quality",
            ))
            return findings, False, VERDICT_NOT_READY, APPROVAL_REJECTED

        for rule in ALL_QUALITY_RULES:
            ok = True
            if rule == RULE_ALL_BLUEPRINTS_PRESENT:
                missing = [i for i in report.issues if i.issue_type == ISSUE_MISSING_BLUEPRINT]
                if missing:
                    findings.append(ReadinessFinding(
                        severity=SEVERITY_CRITICAL, code=rule,
                        message=f"{len(missing)} required blueprint(s) missing.",
                        affected="blueprints", category="completeness"))
                    ok = False
            elif rule == RULE_ALL_VERDICTS_READY:
                not_ready = [i for i in report.issues if i.issue_type == ISSUE_NOT_READY_VERDICT]
                if not_ready:
                    findings.append(ReadinessFinding(
                        severity=SEVERITY_CRITICAL, code=rule,
                        message=f"{len(not_ready)} upstream blueprint(s) still NOT_READY.",
                        affected="verdicts", category="completeness"))
                    ok = False
            elif rule == RULE_NO_CRITICAL_ISSUES:
                crits = [i for i in report.issues if i.severity == SEVERITY_CRITICAL]
                if crits:
                    findings.append(ReadinessFinding(
                        severity=SEVERITY_CRITICAL, code=rule,
                        message=f"{len(crits)} critical issue(s) remain.",
                        affected="issues", category="conflict"))
                    ok = False
            elif rule == RULE_SCORE_100:
                if report.overall_score < REQUIRED_READINESS:
                    findings.append(ReadinessFinding(
                        severity=SEVERITY_CRITICAL, code=rule,
                        message=f"Overall readiness {report.overall_score}% < required {REQUIRED_READINESS}%.",
                        affected="score", category="score"))
                    ok = False
            elif rule == RULE_CONSISTENCY:
                inconsist = [i for i in report.issues if i.issue_type == ISSUE_INCONSISTENCY]
                if inconsist:
                    findings.append(ReadinessFinding(
                        severity=SEVERITY_HIGH, code=rule,
                        message=f"{len(inconsist)} consistency issue(s).",
                        affected="consistency", category="consistency"))
                    ok = False
            elif rule == RULE_SUFFICIENT_CONFIDENCE:
                if report.provenance.confidence < CONFIDENCE_MEDIUM_THRESHOLD:
                    findings.append(ReadinessFinding(
                        severity=SEVERITY_MEDIUM, code=rule,
                        message=f"Confidence {report.provenance.confidence:.2f} below threshold.",
                        affected="provenance", category="quality"))
                    ok = False

            if not ok:
                if rule in (RULE_ALL_BLUEPRINTS_PRESENT, RULE_ALL_VERDICTS_READY,
                            RULE_NO_CRITICAL_ISSUES, RULE_SCORE_100):
                    critical = True
                else:
                    warnings += 1

        if critical or report.overall_score < REQUIRED_READINESS:
            return findings, False, VERDICT_NOT_READY, APPROVAL_REJECTED
        if warnings:
            return findings, True, VERDICT_READY_WITH_WARNINGS, APPROVAL_APPROVED
        return findings, True, VERDICT_READY, APPROVAL_APPROVED


__all__ = ["QualityGate"]
