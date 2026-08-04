"""QualityGate — Specification 052 (MAXIMUM CRITICAL)"""

from __future__ import annotations

from typing import List, Tuple

from .report_data import (
    EngineEcosystemReport, EcosystemFinding,
    SEVERITY_CRITICAL, SEVERITY_HIGH, SEVERITY_MEDIUM,
    RULE_ALL_REGISTERED, RULE_NO_CONFLICTS, RULE_COMPATIBLE,
    RULE_DEPENDENCIES_RESOLVED, RULE_HEALTH_OK, RULE_SELF_VERIFICATION,
    RULE_QUALITY_PASS, ALL_QUALITY_RULES,
    STATUS_REGISTERED, STATUS_ACTIVE, HEALTH_FAILED,
    VERDICT_READY, VERDICT_READY_WITH_WARNINGS, VERDICT_NOT_READY,
)


class QualityGate:
    def validate(
        self, report: EngineEcosystemReport
    ) -> Tuple[List[EcosystemFinding], bool, str]:
        findings: List[EcosystemFinding] = []
        critical_fail = False
        warnings = 0

        for rule in ALL_QUALITY_RULES:
            if rule == RULE_ALL_REGISTERED:
                if report.engine_count == 0:
                    findings.append(EcosystemFinding(
                        severity=SEVERITY_CRITICAL, code=rule,
                        message="No engines registered in ecosystem.",
                        affected="registry", category="registration",
                    ))
                    critical_fail = True
                unregistered = [
                    m for m in report.manifests
                    if m.status not in (STATUS_REGISTERED, STATUS_ACTIVE, "isolated")
                ]
                if unregistered:
                    findings.append(EcosystemFinding(
                        severity=SEVERITY_CRITICAL, code=rule,
                        message=f"{len(unregistered)} engine(s) not properly registered.",
                        affected=",".join(m.engine_id for m in unregistered[:5]),
                        category="registration",
                    ))
                    critical_fail = True

            elif rule == RULE_NO_CONFLICTS or rule == RULE_COMPATIBLE:
                if report.conflict_count > 0:
                    findings.append(EcosystemFinding(
                        severity=SEVERITY_CRITICAL, code=rule,
                        message=f"{report.conflict_count} engine conflict(s) detected.",
                        affected="compatibility", category="conflict",
                        resolution_hint="Resolve version/id/dependency conflicts.",
                    ))
                    critical_fail = True

            elif rule == RULE_DEPENDENCIES_RESOLVED:
                missing = []
                for c in report.compatibility:
                    for conf in c.conflicts:
                        if "missing dependency" in conf:
                            missing.append(c.engine_id)
                if missing:
                    findings.append(EcosystemFinding(
                        severity=SEVERITY_HIGH, code=rule,
                        message=f"Unresolved dependencies for: {', '.join(missing[:5])}",
                        affected=",".join(missing[:5]), category="dependencies",
                    ))
                    warnings += 1

            elif rule == RULE_HEALTH_OK:
                failed = [h for h in report.health if h.status == HEALTH_FAILED]
                # Isolated failures are OK (platform continues)
                if failed and not all(h.isolated for h in failed):
                    findings.append(EcosystemFinding(
                        severity=SEVERITY_HIGH, code=rule,
                        message=f"{len(failed)} engine(s) unhealthy and not isolated.",
                        affected=",".join(h.engine_id for h in failed[:5]),
                        category="health",
                    ))
                    warnings += 1
                if report.isolated_count:
                    findings.append(EcosystemFinding(
                        severity=SEVERITY_MEDIUM, code=rule,
                        message=f"{report.isolated_count} engine(s) isolated after failure.",
                        affected="health", category="isolation",
                    ))
                    warnings += 1

            elif rule == RULE_SELF_VERIFICATION:
                if not report.self_verification_passed:
                    findings.append(EcosystemFinding(
                        severity=SEVERITY_CRITICAL, code=rule,
                        message="Self-verification did not pass.",
                        affected="report", category="self_verification",
                    ))
                    critical_fail = True

            elif rule == RULE_QUALITY_PASS:
                if report.engine_count < 3:
                    findings.append(EcosystemFinding(
                        severity=SEVERITY_MEDIUM, code=rule,
                        message="Very few engines in registry.",
                        affected="registry", category="quality",
                    ))
                    warnings += 1

        if critical_fail:
            return findings, False, VERDICT_NOT_READY
        if warnings > 0 or any(f.severity == SEVERITY_HIGH for f in findings):
            return findings, True, VERDICT_READY_WITH_WARNINGS
        return findings, True, VERDICT_READY


__all__ = ["QualityGate"]
