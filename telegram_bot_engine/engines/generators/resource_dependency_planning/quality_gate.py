"""QualityGate — Specification 025"""

from __future__ import annotations

from typing import List, Tuple

from .report_data import (
    ResourceDependencyBlueprint, ResourceFinding,
    SEVERITY_CRITICAL, SEVERITY_HIGH, SEVERITY_MEDIUM,
    RULE_NO_CRITICAL_CONFLICTS, RULE_NO_VERSION_CONFLICTS, RULE_NO_SECURITY_RISKS,
    RULE_ALL_DEPS_RESOLVED, RULE_ARCHITECTURE_COMPLETE, RULE_SUFFICIENT_CONFIDENCE,
    ALL_QUALITY_RULES, CONFLICT_VERSION, CONFLICT_MISSING_RESOURCE,
    RISK_SECURITY, CONFIDENCE_MEDIUM_THRESHOLD,
    VERDICT_READY, VERDICT_READY_WITH_WARNINGS, VERDICT_NOT_READY,
)


class QualityGate:
    def validate(self, bp: ResourceDependencyBlueprint) -> Tuple[List[ResourceFinding], bool, str]:
        findings: List[ResourceFinding] = []
        critical = False
        warnings = 0

        if bp.is_empty:
            findings.append(ResourceFinding(
                severity=SEVERITY_CRITICAL, code="empty_blueprint",
                message="Resource & Dependency Blueprint is empty.",
                affected="blueprint", category="quality",
            ))
            return findings, False, VERDICT_NOT_READY

        for rule in ALL_QUALITY_RULES:
            ok = True
            if rule == RULE_NO_CRITICAL_CONFLICTS:
                crits = [c for c in bp.conflicts if c.severity == SEVERITY_CRITICAL]
                if crits:
                    findings.append(ResourceFinding(
                        severity=SEVERITY_CRITICAL, code=rule,
                        message=f"{len(crits)} critical conflict(s).",
                        affected="conflicts", category="conflict"))
                    ok = False
            elif rule == RULE_NO_VERSION_CONFLICTS:
                vers = [c for c in bp.conflicts if c.conflict_type == CONFLICT_VERSION]
                if vers:
                    findings.append(ResourceFinding(
                        severity=SEVERITY_HIGH, code=rule,
                        message=f"{len(vers)} version issue(s).",
                        affected="dependencies", category="version"))
                    ok = False
            elif rule == RULE_NO_SECURITY_RISKS:
                secs = [r for r in bp.risks if r.risk_type == RISK_SECURITY and r.severity in ("critical", "high")]
                if secs:
                    findings.append(ResourceFinding(
                        severity=SEVERITY_HIGH, code=rule,
                        message=f"{len(secs)} high/critical security risk(s).",
                        affected="risks", category="security"))
                    ok = False
            elif rule == RULE_ALL_DEPS_RESOLVED:
                missing = [c for c in bp.conflicts if c.conflict_type == CONFLICT_MISSING_RESOURCE]
                if missing:
                    findings.append(ResourceFinding(
                        severity=SEVERITY_CRITICAL, code=rule,
                        message=f"{len(missing)} unresolved required resource(s).",
                        affected="resources", category="structure"))
                    ok = False
            elif rule == RULE_ARCHITECTURE_COMPLETE:
                if not bp.dependencies:
                    findings.append(ResourceFinding(
                        severity=SEVERITY_CRITICAL, code=rule,
                        message="No dependencies defined.",
                        affected="blueprint", category="quality"))
                    ok = False
            elif rule == RULE_SUFFICIENT_CONFIDENCE:
                if bp.provenance.confidence < CONFIDENCE_MEDIUM_THRESHOLD:
                    findings.append(ResourceFinding(
                        severity=SEVERITY_MEDIUM, code=rule,
                        message=f"Confidence {bp.provenance.confidence:.2f} below threshold.",
                        affected="provenance", category="quality"))
                    ok = False

            if not ok:
                if rule in (RULE_NO_CRITICAL_CONFLICTS, RULE_ALL_DEPS_RESOLVED, RULE_ARCHITECTURE_COMPLETE):
                    critical = True
                else:
                    warnings += 1

        if critical:
            return findings, False, VERDICT_NOT_READY
        if warnings:
            return findings, True, VERDICT_READY_WITH_WARNINGS
        return findings, True, VERDICT_READY


__all__ = ["QualityGate"]
