"""QualityGate — Specification 024"""

from __future__ import annotations

import logging
from typing import List, Tuple

from .report_data import (
    DataFlowBlueprint, DataFlowFinding,
    SEVERITY_CRITICAL, SEVERITY_HIGH, SEVERITY_MEDIUM,
    RULE_NO_CRITICAL_CONFLICTS, RULE_NO_LOOPS, RULE_ALL_PATHS_COMPLETE,
    RULE_NO_UNAUTHORIZED, RULE_ARCHITECTURE_COMPLETE, RULE_SUFFICIENT_CONFIDENCE,
    ALL_QUALITY_RULES, CONFLICT_INFINITE_LOOP, CONFLICT_MISSING_PATH,
    CONFLICT_UNAUTHORIZED, CONFIDENCE_MEDIUM_THRESHOLD,
    VERDICT_READY, VERDICT_READY_WITH_WARNINGS, VERDICT_NOT_READY,
)

_log = logging.getLogger("engine.data_flow_planning.quality_gate")


class QualityGate:
    def validate(self, bp: DataFlowBlueprint) -> Tuple[List[DataFlowFinding], bool, str]:
        findings: List[DataFlowFinding] = []
        critical = False
        warnings = 0

        if bp.is_empty:
            findings.append(DataFlowFinding(
                severity=SEVERITY_CRITICAL, code="empty_blueprint",
                message="Data Flow Blueprint is empty.",
                affected="blueprint", category="quality",
            ))
            return findings, False, VERDICT_NOT_READY

        for rule in ALL_QUALITY_RULES:
            ok = True
            if rule == RULE_NO_CRITICAL_CONFLICTS:
                crits = [c for c in bp.conflicts if c.severity == SEVERITY_CRITICAL]
                if crits:
                    findings.append(DataFlowFinding(
                        severity=SEVERITY_CRITICAL, code=rule,
                        message=f"{len(crits)} critical conflict(s).",
                        affected="conflicts", category="conflict"))
                    ok = False
            elif rule == RULE_NO_LOOPS:
                loops = [c for c in bp.conflicts if c.conflict_type == CONFLICT_INFINITE_LOOP]
                if loops:
                    findings.append(DataFlowFinding(
                        severity=SEVERITY_CRITICAL, code=rule,
                        message=f"{len(loops)} infinite-loop path(s).",
                        affected="paths", category="structure"))
                    ok = False
            elif rule == RULE_ALL_PATHS_COMPLETE:
                missing = [c for c in bp.conflicts if c.conflict_type == CONFLICT_MISSING_PATH]
                if missing:
                    findings.append(DataFlowFinding(
                        severity=SEVERITY_CRITICAL, code=rule,
                        message=f"{len(missing)} incomplete path(s).",
                        affected="paths", category="structure"))
                    ok = False
            elif rule == RULE_NO_UNAUTHORIZED:
                unauth = [c for c in bp.conflicts if c.conflict_type == CONFLICT_UNAUTHORIZED]
                if unauth:
                    findings.append(DataFlowFinding(
                        severity=SEVERITY_HIGH, code=rule,
                        message=f"{len(unauth)} unauthorized transfer(s).",
                        affected="security", category="security"))
                    ok = False
            elif rule == RULE_ARCHITECTURE_COMPLETE:
                if not bp.sources or not bp.paths:
                    findings.append(DataFlowFinding(
                        severity=SEVERITY_CRITICAL, code=rule,
                        message="No sources or paths defined.",
                        affected="blueprint", category="quality"))
                    ok = False
            elif rule == RULE_SUFFICIENT_CONFIDENCE:
                if bp.provenance.confidence < CONFIDENCE_MEDIUM_THRESHOLD:
                    findings.append(DataFlowFinding(
                        severity=SEVERITY_MEDIUM, code=rule,
                        message=f"Confidence {bp.provenance.confidence:.2f} below threshold.",
                        affected="provenance", category="quality"))
                    ok = False

            if not ok:
                if rule in (RULE_NO_CRITICAL_CONFLICTS, RULE_NO_LOOPS,
                            RULE_ALL_PATHS_COMPLETE, RULE_ARCHITECTURE_COMPLETE):
                    critical = True
                else:
                    warnings += 1

        if critical:
            return findings, False, VERDICT_NOT_READY
        if warnings:
            return findings, True, VERDICT_READY_WITH_WARNINGS
        return findings, True, VERDICT_READY


__all__ = ["QualityGate"]
