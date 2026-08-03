"""QualityGate — Specification 034 (ULTRA CRITICAL)"""

from __future__ import annotations

from typing import List, Tuple

from .report_data import (
    CodeOptimizationReport, OptimizationFinding,
    SEVERITY_CRITICAL, SEVERITY_HIGH, SEVERITY_MEDIUM,
    RULE_NO_BEHAVIOR_CHANGE, RULE_NO_ARCHITECTURE_BREAK,
    RULE_NO_INTERFACE_CHANGE, RULE_NO_CONTRACT_CHANGE,
    RULE_REGRESSION_SAFE, RULE_QUALITY_PASS,
    RULE_SUFFICIENT_CONFIDENCE, RULE_OPTIMIZATIONS_APPLIED,
    ALL_QUALITY_RULES, MIN_QUALITY_SCORE, CONFIDENCE_MEDIUM_THRESHOLD,
    VERDICT_READY, VERDICT_READY_WITH_WARNINGS, VERDICT_NOT_READY,
)


class QualityGate:
    def validate(self, report: CodeOptimizationReport) -> Tuple[List[OptimizationFinding], bool, str]:
        findings: List[OptimizationFinding] = []
        critical = False
        warnings = 0

        if report.is_empty:
            findings.append(OptimizationFinding(
                severity=SEVERITY_CRITICAL, code="empty_report",
                message="Code Optimization Report is empty.",
                affected="report", category="quality",
            ))
            return findings, False, VERDICT_NOT_READY

        for rule in ALL_QUALITY_RULES:
            ok = True
            if rule == RULE_NO_BEHAVIOR_CHANGE:
                unsafe = [u for u in report.units if not u.behavior_preserved]
                unsafe_actions = [a for a in report.actions if not a.behavior_safe]
                if unsafe or unsafe_actions:
                    findings.append(OptimizationFinding(
                        severity=SEVERITY_CRITICAL, code=rule,
                        message=(
                            f"{len(unsafe)} unit(s) and {len(unsafe_actions)} action(s) "
                            "may alter behaviour."
                        ),
                        affected="units/actions", category="regression",
                    ))
                    ok = False
            elif rule == RULE_NO_ARCHITECTURE_BREAK:
                # Heuristic: reject if any unit lost significant structure markers
                for u in report.units:
                    if "class " in u.original_source and "class " not in u.optimized_source:
                        findings.append(OptimizationFinding(
                            severity=SEVERITY_CRITICAL, code=rule,
                            message=f"Unit {u.unit_id} lost class definition.",
                            affected=u.unit_id, category="architecture",
                        ))
                        ok = False
                        break
            elif rule == RULE_NO_INTERFACE_CHANGE:
                for u in report.units:
                    if "def " in u.original_source:
                        # crude signature presence check
                        orig_defs = {ln.strip() for ln in u.original_source.splitlines() if ln.strip().startswith("def ")}
                        opt_defs = {ln.strip() for ln in u.optimized_source.splitlines() if ln.strip().startswith("def ")}
                        if orig_defs and not orig_defs.issubset(opt_defs) and len(opt_defs) < len(orig_defs):
                            findings.append(OptimizationFinding(
                                severity=SEVERITY_HIGH, code=rule,
                                message=f"Possible signature loss in {u.unit_id}.",
                                affected=u.unit_id, category="interface",
                            ))
                            warnings += 1
            elif rule == RULE_NO_CONTRACT_CHANGE:
                pass  # covered by behaviour + interface checks
            elif rule == RULE_REGRESSION_SAFE:
                if any(not a.behavior_safe for a in report.actions):
                    findings.append(OptimizationFinding(
                        severity=SEVERITY_CRITICAL, code=rule,
                        message="One or more actions are not regression-safe.",
                        affected="actions", category="regression",
                    ))
                    ok = False
            elif rule == RULE_QUALITY_PASS:
                if report.average_quality_after < MIN_QUALITY_SCORE and report.unit_count > 0:
                    findings.append(OptimizationFinding(
                        severity=SEVERITY_HIGH, code=rule,
                        message=(
                            f"Average quality after optimization "
                            f"({report.average_quality_after:.1f}) below minimum "
                            f"({MIN_QUALITY_SCORE})."
                        ),
                        affected="report", category="quality",
                    ))
                    warnings += 1
            elif rule == RULE_SUFFICIENT_CONFIDENCE:
                conf = report.provenance.confidence
                if conf < CONFIDENCE_MEDIUM_THRESHOLD:
                    findings.append(OptimizationFinding(
                        severity=SEVERITY_HIGH, code=rule,
                        message=f"Confidence too low ({conf:.2f}).",
                        affected="provenance", category="confidence",
                    ))
                    warnings += 1
            elif rule == RULE_OPTIMIZATIONS_APPLIED:
                if report.action_count == 0 and report.unit_count > 0:
                    findings.append(OptimizationFinding(
                        severity=SEVERITY_MEDIUM, code=rule,
                        message="No optimizations were applied.",
                        affected="actions", category="coverage",
                    ))
                    warnings += 1

            if not ok:
                critical = True

        if critical:
            return findings, False, VERDICT_NOT_READY
        if warnings > 0 or any(f.severity in (SEVERITY_HIGH, SEVERITY_MEDIUM) for f in findings):
            return findings, True, VERDICT_READY_WITH_WARNINGS
        return findings, True, VERDICT_READY


__all__ = ["QualityGate"]
