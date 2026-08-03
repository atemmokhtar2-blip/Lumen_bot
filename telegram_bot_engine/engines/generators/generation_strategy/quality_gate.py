"""QualityGate — Specification 026"""

from __future__ import annotations

from typing import List, Tuple

from .report_data import (
    GenerationStrategyBlueprint, StrategyFinding,
    SEVERITY_CRITICAL, SEVERITY_HIGH, SEVERITY_MEDIUM,
    RULE_NO_CRITICAL_CONFLICTS, RULE_ALL_STAGES_PRESENT, RULE_ORDER_VALID,
    RULE_NO_EMPTY_FILES, RULE_ARCHITECTURE_COMPLETE, RULE_SUFFICIENT_CONFIDENCE,
    ALL_QUALITY_RULES, CONFLICT_ORDER, CONFLICT_MISSING_STAGE,
    CONFIDENCE_MEDIUM_THRESHOLD,
    VERDICT_READY, VERDICT_READY_WITH_WARNINGS, VERDICT_NOT_READY,
)


class QualityGate:
    def validate(self, bp: GenerationStrategyBlueprint) -> Tuple[List[StrategyFinding], bool, str]:
        findings: List[StrategyFinding] = []
        critical = False
        warnings = 0

        if bp.is_empty:
            findings.append(StrategyFinding(
                severity=SEVERITY_CRITICAL, code="empty_blueprint",
                message="Generation Strategy Blueprint is empty.",
                affected="blueprint", category="quality",
            ))
            return findings, False, VERDICT_NOT_READY

        for rule in ALL_QUALITY_RULES:
            ok = True
            if rule == RULE_NO_CRITICAL_CONFLICTS:
                crits = [c for c in bp.conflicts if c.severity == SEVERITY_CRITICAL]
                if crits:
                    findings.append(StrategyFinding(
                        severity=SEVERITY_CRITICAL, code=rule,
                        message=f"{len(crits)} critical conflict(s).",
                        affected="conflicts", category="conflict"))
                    ok = False
            elif rule == RULE_ALL_STAGES_PRESENT:
                missing = [c for c in bp.conflicts if c.conflict_type == CONFLICT_MISSING_STAGE]
                if missing:
                    findings.append(StrategyFinding(
                        severity=SEVERITY_HIGH, code=rule,
                        message=f"{len(missing)} stage(s) missing.",
                        affected="stages", category="structure"))
                    ok = False
            elif rule == RULE_ORDER_VALID:
                orders = [c for c in bp.conflicts if c.conflict_type == CONFLICT_ORDER]
                if orders:
                    findings.append(StrategyFinding(
                        severity=SEVERITY_CRITICAL, code=rule,
                        message=f"{len(orders)} order violation(s).",
                        affected="generation_order", category="ordering"))
                    ok = False
            elif rule == RULE_NO_EMPTY_FILES:
                if not bp.items:
                    findings.append(StrategyFinding(
                        severity=SEVERITY_CRITICAL, code=rule,
                        message="No generation items planned.",
                        affected="items", category="structure"))
                    ok = False
            elif rule == RULE_ARCHITECTURE_COMPLETE:
                if not bp.stages or not bp.generation_order:
                    findings.append(StrategyFinding(
                        severity=SEVERITY_CRITICAL, code=rule,
                        message="Strategy incomplete (no stages or order).",
                        affected="blueprint", category="quality"))
                    ok = False
            elif rule == RULE_SUFFICIENT_CONFIDENCE:
                if bp.provenance.confidence < CONFIDENCE_MEDIUM_THRESHOLD:
                    findings.append(StrategyFinding(
                        severity=SEVERITY_MEDIUM, code=rule,
                        message=f"Confidence {bp.provenance.confidence:.2f} below threshold.",
                        affected="provenance", category="quality"))
                    ok = False

            if not ok:
                if rule in (RULE_NO_CRITICAL_CONFLICTS, RULE_ORDER_VALID,
                            RULE_NO_EMPTY_FILES, RULE_ARCHITECTURE_COMPLETE):
                    critical = True
                else:
                    warnings += 1

        if critical:
            return findings, False, VERDICT_NOT_READY
        if warnings:
            return findings, True, VERDICT_READY_WITH_WARNINGS
        return findings, True, VERDICT_READY


__all__ = ["QualityGate"]
