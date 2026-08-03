"""QualityGate — Specification 021"""

from __future__ import annotations

import logging
from typing import List, Tuple

from .report_data import (
    ModuleArchitectureBlueprint,
    ArchitectureFinding,
    SEVERITY_CRITICAL,
    SEVERITY_HIGH,
    SEVERITY_MEDIUM,
    RULE_NO_CRITICAL_CONFLICTS,
    RULE_NO_DUPLICATES,
    RULE_NO_OVERLAPPING_RESPONSIBILITIES,
    RULE_NO_CIRCULAR_DEPENDENCIES,
    RULE_ALL_INTERFACES_DEFINED,
    RULE_ARCHITECTURE_COMPLETE,
    RULE_SUFFICIENT_CONFIDENCE,
    ALL_QUALITY_RULES,
    CONFLICT_DUPLICATE_MODULE,
    CONFLICT_CIRCULAR_DEPENDENCY,
    CONFLICT_OVERLAPPING_RESPONSIBILITY,
    CONFIDENCE_MEDIUM_THRESHOLD,
    VERDICT_READY,
    VERDICT_READY_WITH_WARNINGS,
    VERDICT_NOT_READY,
)

_log = logging.getLogger("engine.module_architecture_planning.quality_gate")


class QualityGate:
    def __init__(self) -> None:
        self._findings: List[ArchitectureFinding] = []

    def validate(self, bp: ModuleArchitectureBlueprint) -> Tuple[List[ArchitectureFinding], bool, str]:
        self._findings = []
        critical_failed = False
        warnings = 0

        if bp.is_empty:
            self._findings.append(ArchitectureFinding(
                severity=SEVERITY_CRITICAL, code="empty_blueprint",
                message="Module Architecture Blueprint is empty.",
                affected="blueprint", category="quality",
            ))
            return self._findings, False, VERDICT_NOT_READY

        for rule in ALL_QUALITY_RULES:
            ok = self._check(rule, bp)
            if not ok:
                if rule in (
                    RULE_NO_CRITICAL_CONFLICTS,
                    RULE_NO_DUPLICATES,
                    RULE_NO_CIRCULAR_DEPENDENCIES,
                    RULE_ARCHITECTURE_COMPLETE,
                ):
                    critical_failed = True
                else:
                    warnings += 1

        if critical_failed:
            return self._findings, False, VERDICT_NOT_READY
        if warnings:
            return self._findings, True, VERDICT_READY_WITH_WARNINGS
        return self._findings, True, VERDICT_READY

    def _check(self, rule: str, bp: ModuleArchitectureBlueprint) -> bool:
        if rule == RULE_NO_CRITICAL_CONFLICTS:
            crits = [c for c in bp.conflicts if c.severity == SEVERITY_CRITICAL]
            if crits:
                self._findings.append(ArchitectureFinding(
                    severity=SEVERITY_CRITICAL, code=rule,
                    message=f"{len(crits)} critical conflict(s).",
                    affected="conflicts", category="conflict"))
                return False
            return True
        if rule == RULE_NO_DUPLICATES:
            dups = [c for c in bp.conflicts if c.conflict_type == CONFLICT_DUPLICATE_MODULE]
            if dups:
                self._findings.append(ArchitectureFinding(
                    severity=SEVERITY_CRITICAL, code=rule,
                    message=f"{len(dups)} duplicate module(s).",
                    affected="modules", category="structure"))
                return False
            return True
        if rule == RULE_NO_CIRCULAR_DEPENDENCIES:
            cycles = [c for c in bp.conflicts if c.conflict_type == CONFLICT_CIRCULAR_DEPENDENCY]
            if cycles:
                self._findings.append(ArchitectureFinding(
                    severity=SEVERITY_CRITICAL, code=rule,
                    message=f"{len(cycles)} circular dependency cycle(s).",
                    affected="dependencies", category="dependency"))
                return False
            return True
        if rule == RULE_NO_OVERLAPPING_RESPONSIBILITIES:
            overs = [c for c in bp.conflicts if c.conflict_type == CONFLICT_OVERLAPPING_RESPONSIBILITY]
            if overs:
                self._findings.append(ArchitectureFinding(
                    severity=SEVERITY_HIGH, code=rule,
                    message=f"{len(overs)} overlapping responsibility set(s).",
                    affected="modules", category="structure"))
                return False
            return True
        if rule == RULE_ARCHITECTURE_COMPLETE:
            if not bp.modules:
                self._findings.append(ArchitectureFinding(
                    severity=SEVERITY_CRITICAL, code=rule,
                    message="No modules defined.",
                    affected="blueprint", category="quality"))
                return False
            return True
        if rule == RULE_SUFFICIENT_CONFIDENCE:
            if bp.provenance.confidence < CONFIDENCE_MEDIUM_THRESHOLD:
                self._findings.append(ArchitectureFinding(
                    severity=SEVERITY_MEDIUM, code=rule,
                    message=f"Confidence {bp.provenance.confidence:.2f} below threshold.",
                    affected="provenance", category="quality"))
                return False
            return True
        if rule == RULE_ALL_INTERFACES_DEFINED:
            missing = sum(1 for m in bp.modules if not m.interfaces and m.category in ("core", "business"))
            if missing:
                self._findings.append(ArchitectureFinding(
                    severity=SEVERITY_MEDIUM, code=rule,
                    message=f"{missing} core/business module(s) lack interfaces.",
                    affected="interfaces", category="structure"))
                return False
            return True
        return True


__all__ = ["QualityGate"]
