"""QualityGate — Specification 031 (skeletons only, no business logic)."""

from __future__ import annotations

from typing import List, Tuple

from .report_data import (
    ClassGenerationReport, ClassFinding,
    SEVERITY_CRITICAL, SEVERITY_HIGH, SEVERITY_MEDIUM,
    RULE_NO_DUPLICATES, RULE_NO_CIRCULARS, RULE_NAMING_OK,
    RULE_SKELETONS_ONLY, RULE_ARCHITECTURE_ALIGNED, RULE_SUFFICIENT_CONFIDENCE,
    ALL_QUALITY_RULES, CONFLICT_DUPLICATE_NAME, CONFLICT_CIRCULAR_REF,
    CONFLICT_NAMING, CONFIDENCE_MEDIUM_THRESHOLD,
    VERDICT_READY, VERDICT_READY_WITH_WARNINGS, VERDICT_NOT_READY,
)


class QualityGate:
    def validate(self, report: ClassGenerationReport) -> Tuple[List[ClassFinding], bool, str]:
        findings: List[ClassFinding] = []
        critical = False
        warnings = 0

        if report.is_empty:
            findings.append(ClassFinding(
                severity=SEVERITY_CRITICAL, code="empty_report",
                message="Class Generation Report is empty.",
                affected="report", category="quality",
            ))
            return findings, False, VERDICT_NOT_READY

        for rule in ALL_QUALITY_RULES:
            ok = True
            if rule == RULE_NO_DUPLICATES:
                dups = [c for c in report.conflicts if c.conflict_type == CONFLICT_DUPLICATE_NAME]
                if dups:
                    findings.append(ClassFinding(
                        severity=SEVERITY_CRITICAL, code=rule,
                        message=f"{len(dups)} duplicate class name(s).",
                        affected="classes", category="structure"))
                    ok = False
            elif rule == RULE_NO_CIRCULARS:
                circ = [c for c in report.conflicts if c.conflict_type == CONFLICT_CIRCULAR_REF]
                if circ:
                    findings.append(ClassFinding(
                        severity=SEVERITY_CRITICAL, code=rule,
                        message=f"{len(circ)} circular reference(s).",
                        affected="dependencies", category="circular"))
                    ok = False
            elif rule == RULE_NAMING_OK:
                naming = [c for c in report.conflicts if c.conflict_type == CONFLICT_NAMING]
                if naming:
                    findings.append(ClassFinding(
                        severity=SEVERITY_HIGH, code=rule,
                        message=f"{len(naming)} naming violation(s).",
                        affected="names", category="naming"))
                    ok = False
            elif rule == RULE_SKELETONS_ONLY:
                # Verify no method has a body in source (NotImplementedError only)
                for cls in report.classes:
                    if "business logic" in (cls.source_code or "").lower() and "no business logic" not in (cls.source_code or "").lower():
                        findings.append(ClassFinding(
                            severity=SEVERITY_CRITICAL, code=rule,
                            message=f"Class '{cls.name}' may contain business logic.",
                            affected=cls.class_id, category="skeleton"))
                        ok = False
                        break
                    for m in cls.methods:
                        # body must be None in the model
                        body = m.to_dict().get("body")
                        if body is not None:
                            findings.append(ClassFinding(
                                severity=SEVERITY_CRITICAL, code=rule,
                                message=f"Method '{cls.name}.{m.name}' has a body — forbidden.",
                                affected=cls.class_id, category="skeleton"))
                            ok = False
            elif rule == RULE_ARCHITECTURE_ALIGNED:
                if report.class_count == 0:
                    findings.append(ClassFinding(
                        severity=SEVERITY_CRITICAL, code=rule,
                        message="No classes generated.",
                        affected="classes", category="structure"))
                    ok = False
            elif rule == RULE_SUFFICIENT_CONFIDENCE:
                if report.provenance.confidence < CONFIDENCE_MEDIUM_THRESHOLD:
                    findings.append(ClassFinding(
                        severity=SEVERITY_MEDIUM, code=rule,
                        message=f"Confidence {report.provenance.confidence:.2f} below threshold.",
                        affected="provenance", category="quality"))
                    ok = False

            if not ok:
                if rule in (RULE_NO_DUPLICATES, RULE_NO_CIRCULARS,
                            RULE_SKELETONS_ONLY, RULE_ARCHITECTURE_ALIGNED):
                    critical = True
                else:
                    warnings += 1

        if critical:
            return findings, False, VERDICT_NOT_READY
        if warnings:
            return findings, True, VERDICT_READY_WITH_WARNINGS
        return findings, True, VERDICT_READY


__all__ = ["QualityGate"]
