"""QualityGate — Specification 036 (ULTRA CRITICAL)"""

from __future__ import annotations

from typing import List, Tuple

from .report_data import (
    PerformanceReport, PerformanceFinding,
    SEVERITY_CRITICAL, SEVERITY_HIGH, SEVERITY_MEDIUM,
    RULE_NO_BEHAVIOR_CHANGE, RULE_NO_CRITICAL_BOTTLENECK, RULE_SELF_REVIEW_PASSED,
    RULE_QUALITY_PASS, RULE_SUFFICIENT_CONFIDENCE, RULE_SIMULATION_OK,
    ALL_QUALITY_RULES, MIN_QUALITY_SCORE, CONFIDENCE_MEDIUM_THRESHOLD,
    VERDICT_READY, VERDICT_READY_WITH_WARNINGS, VERDICT_NOT_READY,
    STATUS_OPEN,
)


class QualityGate:
    def validate(self, report: PerformanceReport) -> Tuple[List[PerformanceFinding], bool, str]:
        findings: List[PerformanceFinding] = []
        critical_fail = False
        warnings = 0

        if report.is_empty and report.unit_count == 0:
            findings.append(PerformanceFinding(
                severity=SEVERITY_MEDIUM, code="empty_report",
                message="Performance Report has no units to analyse.",
                affected="report", category="quality",
            ))
            warnings += 1

        for rule in ALL_QUALITY_RULES:
            if rule == RULE_NO_BEHAVIOR_CHANGE:
                unsafe = [a for a in report.actions if not a.behavior_safe]
                if unsafe:
                    findings.append(PerformanceFinding(
                        severity=SEVERITY_CRITICAL, code=rule,
                        message=f"{len(unsafe)} action(s) may alter behaviour.",
                        affected="actions", category="regression",
                        resolution_hint="Reject non behaviour-safe optimisations.",
                    ))
                    critical_fail = True

            elif rule == RULE_NO_CRITICAL_BOTTLENECK:
                open_crit = [
                    b for b in report.bottlenecks
                    if b.severity == SEVERITY_CRITICAL and b.status == STATUS_OPEN
                ]
                if open_crit or report.open_critical_count > 0:
                    findings.append(PerformanceFinding(
                        severity=SEVERITY_CRITICAL, code=rule,
                        message=(
                            f"{len(open_crit) or report.open_critical_count} "
                            "open critical bottleneck(s)."
                        ),
                        affected="bottlenecks", category="performance",
                        resolution_hint="Resolve critical bottlenecks before next engine.",
                    ))
                    critical_fail = True

            elif rule == RULE_SELF_REVIEW_PASSED:
                if not report.self_review_passed:
                    findings.append(PerformanceFinding(
                        severity=SEVERITY_CRITICAL, code=rule,
                        message="Self-review did not pass; residual bottlenecks remain.",
                        affected="report", category="self_review",
                    ))
                    critical_fail = True

            elif rule == RULE_QUALITY_PASS:
                if report.unit_count and report.average_quality_after < MIN_QUALITY_SCORE:
                    findings.append(PerformanceFinding(
                        severity=SEVERITY_HIGH, code=rule,
                        message=(
                            f"Average quality {report.average_quality_after:.1f} "
                            f"< {MIN_QUALITY_SCORE}."
                        ),
                        affected="units", category="quality",
                    ))
                    warnings += 1

            elif rule == RULE_SUFFICIENT_CONFIDENCE:
                conf = report.provenance.confidence if report.provenance else 0.0
                if conf < CONFIDENCE_MEDIUM_THRESHOLD:
                    findings.append(PerformanceFinding(
                        severity=SEVERITY_MEDIUM, code=rule,
                        message=f"Confidence {conf:.2f} below threshold.",
                        affected="provenance", category="confidence",
                    ))
                    warnings += 1

            elif rule == RULE_SIMULATION_OK:
                bad = [
                    s for s in report.simulations
                    if s.users >= 1000 and s.bottleneck_risk == "critical"
                ]
                if bad:
                    findings.append(PerformanceFinding(
                        severity=SEVERITY_HIGH, code=rule,
                        message=(
                            f"Load simulation predicts critical risk at "
                            f"{bad[0].users} users."
                        ),
                        affected="simulations", category="load",
                        resolution_hint="Address critical bottlenecks before scale.",
                    ))
                    warnings += 1

        if critical_fail:
            return findings, False, VERDICT_NOT_READY
        if warnings > 0 or any(f.severity == SEVERITY_HIGH for f in findings):
            return findings, True, VERDICT_READY_WITH_WARNINGS
        return findings, True, VERDICT_READY


__all__ = ["QualityGate"]
