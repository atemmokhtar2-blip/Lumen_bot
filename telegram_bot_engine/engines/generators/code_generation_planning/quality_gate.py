"""QualityGate — Specification 029 v2.0"""

from __future__ import annotations

from typing import List, Tuple

from .report_data import (
    IntelligentCodeGenerationPlan, PlanFinding,
    SEVERITY_CRITICAL, SEVERITY_HIGH, SEVERITY_MEDIUM,
    RULE_QUEUE_COMPLETE, RULE_NO_CIRCULARS, RULE_NO_ORDER_VIOLATIONS,
    RULE_SIMULATION_PASSED, RULE_SCORE_ADEQUATE, RULE_SUFFICIENT_CONFIDENCE,
    ALL_QUALITY_RULES, CONFLICT_CIRCULAR, CONFLICT_ORDER,
    MIN_INTELLIGENCE_SCORE, CONFIDENCE_MEDIUM_THRESHOLD,
    VERDICT_READY, VERDICT_READY_WITH_WARNINGS, VERDICT_NOT_READY,
)


class QualityGate:
    def validate(self, plan: IntelligentCodeGenerationPlan) -> Tuple[List[PlanFinding], bool, str]:
        findings: List[PlanFinding] = []
        critical = False
        warnings = 0

        if plan.is_empty:
            findings.append(PlanFinding(
                severity=SEVERITY_CRITICAL, code="empty_plan",
                message="Intelligent Code Generation Plan is empty.",
                affected="plan", category="quality",
            ))
            return findings, False, VERDICT_NOT_READY

        for rule in ALL_QUALITY_RULES:
            ok = True
            if rule == RULE_QUEUE_COMPLETE:
                if not plan.queue or not plan.units:
                    findings.append(PlanFinding(
                        severity=SEVERITY_CRITICAL, code=rule,
                        message="Generation queue or units are empty.",
                        affected="queue", category="structure"))
                    ok = False
            elif rule == RULE_NO_CIRCULARS:
                circ = [c for c in plan.conflicts if c.conflict_type == CONFLICT_CIRCULAR]
                if circ:
                    findings.append(PlanFinding(
                        severity=SEVERITY_CRITICAL, code=rule,
                        message=f"{len(circ)} circular dependency cycle(s).",
                        affected="dependencies", category="circular"))
                    ok = False
            elif rule == RULE_NO_ORDER_VIOLATIONS:
                orders = [c for c in plan.conflicts if c.conflict_type == CONFLICT_ORDER]
                if orders:
                    findings.append(PlanFinding(
                        severity=SEVERITY_CRITICAL, code=rule,
                        message=f"{len(orders)} order violation(s).",
                        affected="generation_order", category="ordering"))
                    ok = False
            elif rule == RULE_SIMULATION_PASSED:
                if not plan.simulation.passed:
                    findings.append(PlanFinding(
                        severity=SEVERITY_CRITICAL, code=rule,
                        message=f"Simulation failed with {plan.simulation.errors_found} error(s).",
                        affected="simulation", category="simulation"))
                    ok = False
            elif rule == RULE_SCORE_ADEQUATE:
                if plan.overall_intelligence_score < MIN_INTELLIGENCE_SCORE:
                    findings.append(PlanFinding(
                        severity=SEVERITY_HIGH, code=rule,
                        message=f"Intelligence score {plan.overall_intelligence_score} < {MIN_INTELLIGENCE_SCORE}.",
                        affected="score", category="score"))
                    ok = False
            elif rule == RULE_SUFFICIENT_CONFIDENCE:
                if plan.provenance.confidence < CONFIDENCE_MEDIUM_THRESHOLD:
                    findings.append(PlanFinding(
                        severity=SEVERITY_MEDIUM, code=rule,
                        message=f"Confidence {plan.provenance.confidence:.2f} below threshold.",
                        affected="provenance", category="quality"))
                    ok = False

            if not ok:
                if rule in (RULE_QUEUE_COMPLETE, RULE_NO_CIRCULARS,
                            RULE_NO_ORDER_VIOLATIONS, RULE_SIMULATION_PASSED):
                    critical = True
                else:
                    warnings += 1

        if critical:
            return findings, False, VERDICT_NOT_READY
        if warnings:
            return findings, True, VERDICT_READY_WITH_WARNINGS
        return findings, True, VERDICT_READY


__all__ = ["QualityGate"]
