"""
QualityGate — Specification 020
"""

from __future__ import annotations

import logging
from typing import List, Tuple

from .report_data import (
    ProjectStructureBlueprint,
    StructureFinding,
    SEVERITY_CRITICAL,
    SEVERITY_HIGH,
    SEVERITY_MEDIUM,
    RULE_NO_CRITICAL_CONFLICTS,
    RULE_NO_DUPLICATES,
    RULE_NO_UNUSED_FOLDERS,
    RULE_NO_NAME_COLLISIONS,
    RULE_NO_CIRCULAR_STRUCTURE,
    RULE_STRUCTURE_COMPLETE,
    RULE_SUFFICIENT_CONFIDENCE,
    ALL_QUALITY_RULES,
    CONFLICT_DUPLICATE_FILE,
    CONFLICT_CIRCULAR_STRUCTURE,
    CONFIDENCE_MEDIUM_THRESHOLD,
    VERDICT_READY,
    VERDICT_READY_WITH_WARNINGS,
    VERDICT_NOT_READY,
)

_log = logging.getLogger("engine.project_structure_planning.quality_gate")


class QualityGate:
    def __init__(self) -> None:
        self._findings: List[StructureFinding] = []

    def validate(self, blueprint: ProjectStructureBlueprint) -> Tuple[List[StructureFinding], bool, str]:
        self._findings = []
        critical_failed = False
        warning_count = 0

        if blueprint.is_empty:
            self._findings.append(StructureFinding(
                severity=SEVERITY_CRITICAL, code="empty_blueprint",
                message="Project Structure Blueprint is empty.",
                affected="blueprint", category="quality",
            ))
            return self._findings, False, VERDICT_NOT_READY

        for rule in ALL_QUALITY_RULES:
            ok = self._check(rule, blueprint)
            if not ok:
                if rule in (RULE_NO_CRITICAL_CONFLICTS, RULE_NO_DUPLICATES,
                            RULE_NO_CIRCULAR_STRUCTURE, RULE_STRUCTURE_COMPLETE):
                    critical_failed = True
                else:
                    warning_count += 1

        if critical_failed:
            return self._findings, False, VERDICT_NOT_READY
        if warning_count > 0:
            return self._findings, True, VERDICT_READY_WITH_WARNINGS
        return self._findings, True, VERDICT_READY

    def _check(self, rule: str, bp: ProjectStructureBlueprint) -> bool:
        if rule == RULE_NO_CRITICAL_CONFLICTS:
            crits = [c for c in bp.conflicts if c.severity == SEVERITY_CRITICAL]
            if crits:
                self._findings.append(StructureFinding(
                    severity=SEVERITY_CRITICAL, code=rule,
                    message=f"{len(crits)} critical conflict(s) present.",
                    affected="conflicts", category="conflict"))
                return False
            return True
        if rule == RULE_NO_DUPLICATES:
            dups = [c for c in bp.conflicts if c.conflict_type == CONFLICT_DUPLICATE_FILE]
            if dups:
                self._findings.append(StructureFinding(
                    severity=SEVERITY_CRITICAL, code=rule,
                    message=f"{len(dups)} duplicate file path(s).",
                    affected="files", category="structure"))
                return False
            return True
        if rule == RULE_NO_CIRCULAR_STRUCTURE:
            cycles = [c for c in bp.conflicts if c.conflict_type == CONFLICT_CIRCULAR_STRUCTURE]
            if cycles:
                self._findings.append(StructureFinding(
                    severity=SEVERITY_CRITICAL, code=rule,
                    message=f"{len(cycles)} circular structure(s).",
                    affected="dependencies", category="dependency"))
                return False
            return True
        if rule == RULE_STRUCTURE_COMPLETE:
            if not bp.folders or not bp.files:
                self._findings.append(StructureFinding(
                    severity=SEVERITY_CRITICAL, code=rule,
                    message="Structure is incomplete (no folders or no files).",
                    affected="blueprint", category="quality"))
                return False
            return True
        if rule == RULE_SUFFICIENT_CONFIDENCE:
            if bp.provenance.confidence < CONFIDENCE_MEDIUM_THRESHOLD:
                self._findings.append(StructureFinding(
                    severity=SEVERITY_MEDIUM, code=rule,
                    message=f"Confidence {bp.provenance.confidence:.2f} below threshold.",
                    affected="provenance", category="quality"))
                return False
            return True
        # soft rules
        if rule == RULE_NO_UNUSED_FOLDERS:
            unused = [c for c in bp.conflicts if c.conflict_type == "unused_folder"]
            if unused:
                self._findings.append(StructureFinding(
                    severity=SEVERITY_MEDIUM, code=rule,
                    message=f"{len(unused)} unused folder(s).",
                    affected="folders", category="structure"))
                return False
            return True
        if rule == RULE_NO_NAME_COLLISIONS:
            coll = [c for c in bp.conflicts if c.conflict_type == "name_collision"]
            if coll:
                self._findings.append(StructureFinding(
                    severity=SEVERITY_MEDIUM, code=rule,
                    message=f"{len(coll)} name collision(s).",
                    affected="files", category="structure"))
                return False
            return True
        return True


__all__ = ["QualityGate"]
