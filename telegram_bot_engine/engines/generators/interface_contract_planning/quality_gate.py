"""QualityGate — Specification 023"""

from __future__ import annotations

import logging
from typing import List, Tuple

from .report_data import (
    InterfaceContractBlueprint,
    InterfaceFinding,
    SEVERITY_CRITICAL,
    SEVERITY_HIGH,
    SEVERITY_MEDIUM,
    RULE_NO_CRITICAL_CONFLICTS,
    RULE_NO_DUPLICATES,
    RULE_ALL_CONTRACTS_DEFINED,
    RULE_NO_STRONG_COUPLING,
    RULE_ARCHITECTURE_COMPLETE,
    RULE_SUFFICIENT_CONFIDENCE,
    ALL_QUALITY_RULES,
    CONFLICT_DUPLICATE_INTERFACE,
    CONFLICT_MISSING_CONTRACT,
    CONFLICT_STRONG_COUPLING,
    CONFIDENCE_MEDIUM_THRESHOLD,
    VERDICT_READY,
    VERDICT_READY_WITH_WARNINGS,
    VERDICT_NOT_READY,
)

_log = logging.getLogger("engine.interface_contract_planning.quality_gate")


class QualityGate:
    def validate(self, bp: InterfaceContractBlueprint) -> Tuple[List[InterfaceFinding], bool, str]:
        findings: List[InterfaceFinding] = []
        critical = False
        warnings = 0

        if bp.is_empty:
            findings.append(InterfaceFinding(
                severity=SEVERITY_CRITICAL, code="empty_blueprint",
                message="Interface & Contract Blueprint is empty.",
                affected="blueprint", category="quality",
            ))
            return findings, False, VERDICT_NOT_READY

        for rule in ALL_QUALITY_RULES:
            ok = True
            if rule == RULE_NO_CRITICAL_CONFLICTS:
                crits = [c for c in bp.conflicts if c.severity == SEVERITY_CRITICAL]
                if crits:
                    findings.append(InterfaceFinding(
                        severity=SEVERITY_CRITICAL, code=rule,
                        message=f"{len(crits)} critical conflict(s).",
                        affected="conflicts", category="conflict"))
                    ok = False
            elif rule == RULE_NO_DUPLICATES:
                dups = [c for c in bp.conflicts if c.conflict_type == CONFLICT_DUPLICATE_INTERFACE]
                if dups:
                    findings.append(InterfaceFinding(
                        severity=SEVERITY_CRITICAL, code=rule,
                        message=f"{len(dups)} duplicate interface(s).",
                        affected="interfaces", category="structure"))
                    ok = False
            elif rule == RULE_ALL_CONTRACTS_DEFINED:
                missing = [c for c in bp.conflicts if c.conflict_type == CONFLICT_MISSING_CONTRACT]
                if missing:
                    findings.append(InterfaceFinding(
                        severity=SEVERITY_HIGH, code=rule,
                        message=f"{len(missing)} interface(s) lack contracts.",
                        affected="contracts", category="structure"))
                    ok = False
            elif rule == RULE_NO_STRONG_COUPLING:
                strong = [c for c in bp.conflicts if c.conflict_type == CONFLICT_STRONG_COUPLING]
                if strong:
                    findings.append(InterfaceFinding(
                        severity=SEVERITY_MEDIUM, code=rule,
                        message=f"{len(strong)} strong-coupling warning(s).",
                        affected="interfaces", category="dependency"))
                    ok = False
            elif rule == RULE_ARCHITECTURE_COMPLETE:
                if not bp.interfaces or not bp.contracts:
                    findings.append(InterfaceFinding(
                        severity=SEVERITY_CRITICAL, code=rule,
                        message="No interfaces or contracts defined.",
                        affected="blueprint", category="quality"))
                    ok = False
            elif rule == RULE_SUFFICIENT_CONFIDENCE:
                if bp.provenance.confidence < CONFIDENCE_MEDIUM_THRESHOLD:
                    findings.append(InterfaceFinding(
                        severity=SEVERITY_MEDIUM, code=rule,
                        message=f"Confidence {bp.provenance.confidence:.2f} below threshold.",
                        affected="provenance", category="quality"))
                    ok = False

            if not ok:
                if rule in (RULE_NO_CRITICAL_CONFLICTS, RULE_NO_DUPLICATES, RULE_ARCHITECTURE_COMPLETE):
                    critical = True
                else:
                    warnings += 1

        if critical:
            return findings, False, VERDICT_NOT_READY
        if warnings:
            return findings, True, VERDICT_READY_WITH_WARNINGS
        return findings, True, VERDICT_READY


__all__ = ["QualityGate"]
