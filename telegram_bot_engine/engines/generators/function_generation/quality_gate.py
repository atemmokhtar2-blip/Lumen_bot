"""QualityGate — Specification 032"""

from __future__ import annotations

from typing import List, Tuple

from .report_data import (
    FunctionGenerationReport, MethodFinding,
    SEVERITY_CRITICAL, SEVERITY_HIGH, SEVERITY_MEDIUM,
    RULE_NO_DUPLICATES, RULE_NO_SIGNATURE_CLASH, RULE_SKELETONS_ONLY,
    RULE_ALL_CLASSES_COVERED, RULE_SUFFICIENT_CONFIDENCE,
    ALL_QUALITY_RULES, CONFLICT_DUPLICATE_METHOD, CONFLICT_SIGNATURE_CLASH,
    CONFIDENCE_MEDIUM_THRESHOLD,
    VERDICT_READY, VERDICT_READY_WITH_WARNINGS, VERDICT_NOT_READY,
)


class QualityGate:
    def validate(self, report: FunctionGenerationReport) -> Tuple[List[MethodFinding], bool, str]:
        findings: List[MethodFinding] = []
        critical = False
        warnings = 0

        if report.is_empty:
            findings.append(MethodFinding(
                severity=SEVERITY_CRITICAL, code="empty_report",
                message="Function Generation Report is empty.",
                affected="report", category="quality",
            ))
            return findings, False, VERDICT_NOT_READY

        for rule in ALL_QUALITY_RULES:
            ok = True
            if rule == RULE_NO_DUPLICATES:
                dups = [c for c in report.conflicts if c.conflict_type == CONFLICT_DUPLICATE_METHOD]
                if dups:
                    findings.append(MethodFinding(
                        severity=SEVERITY_CRITICAL, code=rule,
                        message=f"{len(dups)} duplicate method(s).",
                        affected="methods", category="structure"))
                    ok = False
            elif rule == RULE_NO_SIGNATURE_CLASH:
                clashes = [c for c in report.conflicts if c.conflict_type == CONFLICT_SIGNATURE_CLASH]
                if clashes:
                    findings.append(MethodFinding(
                        severity=SEVERITY_CRITICAL, code=rule,
                        message=f"{len(clashes)} signature clash(es).",
                        affected="methods", category="structure"))
                    ok = False
            elif rule == RULE_SKELETONS_ONLY:
                for m in report.methods:
                    if m.body is not None:
                        findings.append(MethodFinding(
                            severity=SEVERITY_CRITICAL, code=rule,
                            message=f"Method '{m.name}' has a body — forbidden.",
                            affected=m.method_id, category="skeleton"))
                        ok = False
                        break
            elif rule == RULE_ALL_CLASSES_COVERED:
                if report.method_count == 0:
                    findings.append(MethodFinding(
                        severity=SEVERITY_CRITICAL, code=rule,
                        message="No methods generated.",
                        affected="methods", category="structure"))
                    ok = False
            elif rule == RULE_SUFFICIENT_CONFIDENCE:
                if report.provenance.confidence < CONFIDENCE_MEDIUM_THRESHOLD:
                    findings.append(MethodFinding(
                        severity=SEVERITY_MEDIUM, code=rule,
                        message=f"Confidence {report.provenance.confidence:.2f} below threshold.",
                        affected="provenance", category="quality"))
                    ok = False

            if not ok:
                if rule in (RULE_NO_DUPLICATES, RULE_NO_SIGNATURE_CLASH,
                            RULE_SKELETONS_ONLY, RULE_ALL_CLASSES_COVERED):
                    critical = True
                else:
                    warnings += 1

        if critical:
            return findings, False, VERDICT_NOT_READY
        if warnings:
            return findings, True, VERDICT_READY_WITH_WARNINGS
        return findings, True, VERDICT_READY


__all__ = ["QualityGate"]
