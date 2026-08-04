"""QualityGate — Specification 061 (MAXIMUM CRITICAL)"""

from __future__ import annotations

from typing import List, Tuple

from .report_data import (
    ServiceManagementReport, ServiceFinding,
    SEVERITY_CRITICAL, SEVERITY_HIGH, SEVERITY_MEDIUM,
    RULE_REGISTERED_ONLY, RULE_DEPENDENCY_ORDER, RULE_HEALTH_TRACKED,
    RULE_ISOLATION, RULE_SELF_VERIFICATION, RULE_QUALITY_PASS,
    ALL_QUALITY_RULES,
    VERDICT_READY, VERDICT_READY_WITH_WARNINGS, VERDICT_NOT_READY,
    STATE_STARTED, STATE_FAILED,
)


class QualityGate:
    def validate(
        self, report: ServiceManagementReport
    ) -> Tuple[List[ServiceFinding], bool, str]:
        findings: List[ServiceFinding] = []
        critical_fail = False
        warnings = 0

        for rule in ALL_QUALITY_RULES:
            if rule == RULE_REGISTERED_ONLY:
                if report.unregistered_attempts > 0:
                    findings.append(ServiceFinding(
                        severity=SEVERITY_CRITICAL, code=rule,
                        message=(
                            f"{report.unregistered_attempts} attempt(s) to run "
                            "services outside the registry."
                        ),
                        affected="registry", category="policy",
                        resolution_hint="Register all services before start.",
                    ))
                    critical_fail = True

            elif rule == RULE_DEPENDENCY_ORDER:
                if report.dependency_violations > 0:
                    findings.append(ServiceFinding(
                        severity=SEVERITY_CRITICAL, code=rule,
                        message=(
                            f"{report.dependency_violations} dependency order "
                            "violation(s)."
                        ),
                        affected="lifecycle", category="dependencies",
                    ))
                    critical_fail = True

            elif rule == RULE_HEALTH_TRACKED:
                if report.service_count > 0 and not report.health:
                    findings.append(ServiceFinding(
                        severity=SEVERITY_CRITICAL, code=rule,
                        message="No health metrics collected.",
                        affected="health", category="health",
                    ))
                    critical_fail = True
                unhealthy = [h for h in report.health if h.status == "unhealthy"]
                if unhealthy and report.recovery_count == 0:
                    findings.append(ServiceFinding(
                        severity=SEVERITY_HIGH, code=rule,
                        message=f"{len(unhealthy)} unhealthy service(s) without recovery.",
                        affected=",".join(h.service_id for h in unhealthy[:5]),
                        category="health",
                    ))
                    warnings += 1

            elif rule == RULE_ISOLATION:
                # Failed services should not leave others failed if isolation works
                failed = [s for s in report.services if s.state == STATE_FAILED]
                started = [s for s in report.services if s.state == STATE_STARTED]
                if failed and not started and report.service_count > len(failed):
                    findings.append(ServiceFinding(
                        severity=SEVERITY_HIGH, code=rule,
                        message="Service failure cascaded; isolation may be weak.",
                        affected="isolation", category="isolation",
                    ))
                    warnings += 1

            elif rule == RULE_SELF_VERIFICATION:
                if not report.self_verification_passed:
                    findings.append(ServiceFinding(
                        severity=SEVERITY_CRITICAL, code=rule,
                        message="Self-verification did not pass.",
                        affected="report", category="self_verification",
                    ))
                    critical_fail = True

            elif rule == RULE_QUALITY_PASS:
                if report.service_count == 0:
                    findings.append(ServiceFinding(
                        severity=SEVERITY_CRITICAL, code=rule,
                        message="No services registered.",
                        affected="services", category="quality",
                    ))
                    critical_fail = True
                if report.started_count == 0 and report.service_count > 0:
                    findings.append(ServiceFinding(
                        severity=SEVERITY_HIGH, code=rule,
                        message="No services reached started state.",
                        affected="lifecycle", category="quality",
                    ))
                    warnings += 1
                if not report.lifecycle_events:
                    findings.append(ServiceFinding(
                        severity=SEVERITY_HIGH, code=rule,
                        message="Lifecycle event log is empty.",
                        affected="lifecycle", category="quality",
                    ))
                    warnings += 1

        if critical_fail:
            return findings, False, VERDICT_NOT_READY
        if warnings > 0 or any(f.severity == SEVERITY_HIGH for f in findings):
            return findings, True, VERDICT_READY_WITH_WARNINGS
        return findings, True, VERDICT_READY


__all__ = ["QualityGate"]
