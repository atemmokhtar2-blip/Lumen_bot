"""QualityGate — Specification 037 (ULTRA CRITICAL)"""

from __future__ import annotations

from typing import List, Tuple

from .report_data import (
    ArchitectureComplianceReport, ComplianceFinding,
    SEVERITY_CRITICAL, SEVERITY_HIGH, SEVERITY_MEDIUM,
    RULE_NO_ARCHITECTURE_VIOLATION, RULE_SOLID_COMPLIANT, RULE_LAYERS_RESPECTED,
    RULE_DEPENDENCIES_VALID, RULE_INTERFACES_HONOURED, RULE_SELF_REVIEW_PASSED,
    RULE_QUALITY_PASS, RULE_SUFFICIENT_CONFIDENCE,
    ALL_QUALITY_RULES, MIN_COMPLIANCE_SCORE, CONFIDENCE_MEDIUM_THRESHOLD,
    VERDICT_READY, VERDICT_READY_WITH_WARNINGS, VERDICT_NOT_READY,
    STATUS_OPEN,
    VIO_LAYER_BYPASS, VIO_CIRCULAR_DEPENDENCY, VIO_DIP, VIO_CONTRACT_BREAK,
    VIO_SRP, VIO_MISSING_INTERFACE,
)


class QualityGate:
    def validate(
        self, report: ArchitectureComplianceReport
    ) -> Tuple[List[ComplianceFinding], bool, str]:
        findings: List[ComplianceFinding] = []
        critical_fail = False
        warnings = 0

        if report.is_empty and report.unit_count == 0:
            findings.append(ComplianceFinding(
                severity=SEVERITY_MEDIUM, code="empty_report",
                message="Architecture Compliance Report has no units.",
                affected="report", category="quality",
            ))
            warnings += 1

        open_v = [v for v in report.violations if v.status == STATUS_OPEN]

        for rule in ALL_QUALITY_RULES:
            if rule == RULE_NO_ARCHITECTURE_VIOLATION:
                crit = [
                    v for v in open_v
                    if v.severity == SEVERITY_CRITICAL
                ]
                if crit or report.critical_violation_count > 0:
                    findings.append(ComplianceFinding(
                        severity=SEVERITY_CRITICAL, code=rule,
                        message=(
                            f"{len(crit) or report.critical_violation_count} "
                            "critical architecture violation(s)."
                        ),
                        affected="architecture", category="compliance",
                        resolution_hint="Resolve critical violations before continuing.",
                    ))
                    critical_fail = True
                elif open_v:
                    findings.append(ComplianceFinding(
                        severity=SEVERITY_HIGH, code=rule,
                        message=f"{len(open_v)} open architecture violation(s).",
                        affected="architecture", category="compliance",
                    ))
                    # Spec: any architecture violation blocks next engine
                    critical_fail = True

            elif rule == RULE_SOLID_COMPLIANT:
                solid_v = [
                    v for v in open_v
                    if v.violation_type in (VIO_SRP, VIO_DIP)
                ]
                if solid_v:
                    findings.append(ComplianceFinding(
                        severity=SEVERITY_HIGH, code=rule,
                        message=f"{len(solid_v)} SOLID-related violation(s).",
                        affected="classes", category="solid",
                    ))
                    warnings += 1
                if report.solid_score < MIN_COMPLIANCE_SCORE:
                    findings.append(ComplianceFinding(
                        severity=SEVERITY_HIGH, code=rule,
                        message=f"SOLID score {report.solid_score:.1f} < {MIN_COMPLIANCE_SCORE}.",
                        affected="units", category="solid",
                    ))
                    warnings += 1

            elif rule == RULE_LAYERS_RESPECTED:
                layer_v = [v for v in open_v if v.violation_type == VIO_LAYER_BYPASS]
                if layer_v:
                    findings.append(ComplianceFinding(
                        severity=SEVERITY_CRITICAL, code=rule,
                        message=f"{len(layer_v)} layer bypass violation(s).",
                        affected="layers", category="layers",
                    ))
                    critical_fail = True

            elif rule == RULE_DEPENDENCIES_VALID:
                dep_v = [
                    v for v in open_v
                    if v.violation_type in (VIO_CIRCULAR_DEPENDENCY, VIO_UNEXPECTED_DEPENDENCY)
                ]
                if dep_v:
                    findings.append(ComplianceFinding(
                        severity=SEVERITY_CRITICAL, code=rule,
                        message=f"{len(dep_v)} dependency violation(s).",
                        affected="dependencies", category="dependencies",
                    ))
                    critical_fail = True

            elif rule == RULE_INTERFACES_HONOURED:
                iface_v = [
                    v for v in open_v
                    if v.violation_type in (VIO_MISSING_INTERFACE, VIO_CONTRACT_BREAK)
                ]
                if iface_v:
                    findings.append(ComplianceFinding(
                        severity=SEVERITY_HIGH, code=rule,
                        message=f"{len(iface_v)} interface/contract issue(s).",
                        affected="interfaces", category="interfaces",
                    ))
                    warnings += 1

            elif rule == RULE_SELF_REVIEW_PASSED:
                if not report.self_review_passed:
                    findings.append(ComplianceFinding(
                        severity=SEVERITY_CRITICAL, code=rule,
                        message="Self-review did not pass.",
                        affected="report", category="self_review",
                    ))
                    critical_fail = True

            elif rule == RULE_QUALITY_PASS:
                if report.compliance_score < MIN_COMPLIANCE_SCORE:
                    findings.append(ComplianceFinding(
                        severity=SEVERITY_CRITICAL, code=rule,
                        message=(
                            f"Compliance score {report.compliance_score:.1f} "
                            f"< {MIN_COMPLIANCE_SCORE}."
                        ),
                        affected="report", category="quality",
                    ))
                    critical_fail = True

            elif rule == RULE_SUFFICIENT_CONFIDENCE:
                conf = report.provenance.confidence if report.provenance else 0.0
                if conf < CONFIDENCE_MEDIUM_THRESHOLD:
                    findings.append(ComplianceFinding(
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
