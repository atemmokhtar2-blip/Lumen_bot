"""QualityGate — Specification 022"""

from __future__ import annotations

import logging
from typing import List, Tuple

from .report_data import (
    ComponentArchitectureBlueprint,
    ComponentFinding,
    SEVERITY_CRITICAL,
    SEVERITY_HIGH,
    SEVERITY_MEDIUM,
    RULE_NO_CRITICAL_CONFLICTS,
    RULE_NO_DUPLICATES,
    RULE_NO_OVERLAPPING,
    RULE_NO_CIRCULAR,
    RULE_ARCHITECTURE_COMPLETE,
    RULE_SUFFICIENT_CONFIDENCE,
    ALL_QUALITY_RULES,
    CONFLICT_DUPLICATE_COMPONENT,
    CONFLICT_CIRCULAR_DEPENDENCY,
    CONFLICT_OVERLAPPING_RESPONSIBILITY,
    CONFIDENCE_MEDIUM_THRESHOLD,
    VERDICT_READY,
    VERDICT_READY_WITH_WARNINGS,
    VERDICT_NOT_READY,
)

_log = logging.getLogger("engine.component_architecture_planning.quality_gate")


class QualityGate:
    def validate(self, bp: ComponentArchitectureBlueprint) -> Tuple[List[ComponentFinding], bool, str]:
        findings: List[ComponentFinding] = []
        critical = False
        warnings = 0

        if bp.is_empty:
            findings.append(ComponentFinding(
                severity=SEVERITY_CRITICAL, code="empty_blueprint",
                message="Component Architecture Blueprint is empty.",
                affected="blueprint", category="quality",
            ))
            return findings, False, VERDICT_NOT_READY

        for rule in ALL_QUALITY_RULES:
            ok = True
            if rule == RULE_NO_CRITICAL_CONFLICTS:
                crits = [c for c in bp.conflicts if c.severity == SEVERITY_CRITICAL]
                if crits:
                    findings.append(ComponentFinding(
                        severity=SEVERITY_CRITICAL, code=rule,
                        message=f"{len(crits)} critical conflict(s).",
                        affected="conflicts", category="conflict"))
                    ok = False
            elif rule == RULE_NO_DUPLICATES:
                dups = [c for c in bp.conflicts if c.conflict_type == CONFLICT_DUPLICATE_COMPONENT]
                if dups:
                    findings.append(ComponentFinding(
                        severity=SEVERITY_CRITICAL, code=rule,
                        message=f"{len(dups)} duplicate component(s).",
                        affected="components", category="structure"))
                    ok = False
            elif rule == RULE_NO_CIRCULAR:
                cycles = [c for c in bp.conflicts if c.conflict_type == CONFLICT_CIRCULAR_DEPENDENCY]
                if cycles:
                    findings.append(ComponentFinding(
                        severity=SEVERITY_CRITICAL, code=rule,
                        message=f"{len(cycles)} circular dependency cycle(s).",
                        affected="dependencies", category="dependency"))
                    ok = False
            elif rule == RULE_NO_OVERLAPPING:
                overs = [c for c in bp.conflicts if c.conflict_type == CONFLICT_OVERLAPPING_RESPONSIBILITY]
                if overs:
                    findings.append(ComponentFinding(
                        severity=SEVERITY_HIGH, code=rule,
                        message=f"{len(overs)} overlapping responsibility set(s).",
                        affected="components", category="structure"))
                    ok = False
            elif rule == RULE_ARCHITECTURE_COMPLETE:
                if not bp.components:
                    findings.append(ComponentFinding(
                        severity=SEVERITY_CRITICAL, code=rule,
                        message="No components defined.",
                        affected="blueprint", category="quality"))
                    ok = False
            elif rule == RULE_SUFFICIENT_CONFIDENCE:
                if bp.provenance.confidence < CONFIDENCE_MEDIUM_THRESHOLD:
                    findings.append(ComponentFinding(
                        severity=SEVERITY_MEDIUM, code=rule,
                        message=f"Confidence {bp.provenance.confidence:.2f} below threshold.",
                        affected="provenance", category="quality"))
                    ok = False

            if not ok:
                if rule in (RULE_NO_CRITICAL_CONFLICTS, RULE_NO_DUPLICATES,
                            RULE_NO_CIRCULAR, RULE_ARCHITECTURE_COMPLETE):
                    critical = True
                else:
                    warnings += 1

        if critical:
            return findings, False, VERDICT_NOT_READY
        if warnings:
            return findings, True, VERDICT_READY_WITH_WARNINGS
        return findings, True, VERDICT_READY


__all__ = ["QualityGate"]
