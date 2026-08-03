"""QualityGate — Specification 039 (ULTRA CRITICAL)"""

from __future__ import annotations

from typing import List, Tuple

from .report_data import (
    StaticAnalysisReport, StaticFinding,
    SEVERITY_CRITICAL, SEVERITY_HIGH, SEVERITY_MEDIUM,
    RULE_NO_CRITICAL, RULE_SYNTAX_CLEAN, RULE_REFS_RESOLVED,
    RULE_SELF_VERIFICATION, RULE_QUALITY_PASS, RULE_SUFFICIENT_CONFIDENCE,
    ALL_QUALITY_RULES, CONFIDENCE_MEDIUM_THRESHOLD,
    VERDICT_READY, VERDICT_READY_WITH_WARNINGS, VERDICT_NOT_READY,
    STATUS_OPEN, ISSUE_SYNTAX, ISSUE_PARSE,
)


class QualityGate:
    def validate(
        self, report: StaticAnalysisReport
    ) -> Tuple[List[StaticFinding], bool, str]:
        findings: List[StaticFinding] = []
        critical_fail = False
        warnings = 0

        if report.is_empty and report.unit_count == 0:
            findings.append(StaticFinding(
                severity=SEVERITY_MEDIUM, code="empty_report",
                message="Static Analysis Report has no units.",
                affected="report", category="quality",
            ))
            warnings += 1

        open_issues = [i for i in report.issues if i.status == STATUS_OPEN]

        for rule in ALL_QUALITY_RULES:
            if rule == RULE_NO_CRITICAL:
                crit = [
                    i for i in open_issues if i.severity == SEVERITY_CRITICAL
                ]
                if crit or report.open_critical_count > 0:
                    findings.append(StaticFinding(
                        severity=SEVERITY_CRITICAL, code=rule,
                        message=(
                            f"{len(crit) or report.open_critical_count} "
                            "open critical issue(s)."
                        ),
                        affected="issues", category="static",
                        resolution_hint="Critical issues cannot be ignored.",
                    ))
                    critical_fail = True

            elif rule == RULE_SYNTAX_CLEAN:
                syntax = [
                    i for i in open_issues
                    if i.issue_type in (ISSUE_SYNTAX, ISSUE_PARSE)
                ]
                bad_units = [u for u in report.units if not u.syntax_ok]
                if syntax or bad_units:
                    findings.append(StaticFinding(
                        severity=SEVERITY_CRITICAL, code=rule,
                        message=(
                            f"{len(syntax)} syntax/parse issue(s), "
                            f"{len(bad_units)} unit(s) failed syntax."
                        ),
                        affected="syntax", category="syntax",
                    ))
                    critical_fail = True

            elif rule == RULE_REFS_RESOLVED:
                # informational: broken refs already in issues
                pass

            elif rule == RULE_SELF_VERIFICATION:
                if not report.self_verification_passed:
                    findings.append(StaticFinding(
                        severity=SEVERITY_CRITICAL, code=rule,
                        message="Self-verification did not pass.",
                        affected="report", category="self_verification",
                    ))
                    critical_fail = True

            elif rule == RULE_QUALITY_PASS:
                high = [i for i in open_issues if i.severity == SEVERITY_HIGH]
                if len(high) > 10:
                    findings.append(StaticFinding(
                        severity=SEVERITY_HIGH, code=rule,
                        message=f"Many high-severity issues ({len(high)}).",
                        affected="issues", category="quality",
                    ))
                    warnings += 1

            elif rule == RULE_SUFFICIENT_CONFIDENCE:
                conf = report.provenance.confidence if report.provenance else 0.0
                if conf < CONFIDENCE_MEDIUM_THRESHOLD:
                    findings.append(StaticFinding(
                        severity=SEVERITY_MEDIUM, code=rule,
                        message=f"Confidence {conf:.2f} below threshold.",
                        affected="provenance", category="confidence",
                    ))
                    warnings += 1

        if critical_fail:
            return findings, False, VERDICT_NOT_READY
        if warnings > 0 or any(f.severity == SEVERITY_HIGH for f in findings):
            return findings, True, VERDICT_READY_WITH_WARNINGS
        return findings, True, VERDICT_READY


__all__ = ["QualityGate"]
