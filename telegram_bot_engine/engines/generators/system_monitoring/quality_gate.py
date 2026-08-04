"""QualityGate — Specification 057 (CRITICAL)"""

from __future__ import annotations

from typing import List, Tuple

from .report_data import (
    SystemMonitoringReport, MonitoringFinding,
    SEVERITY_CRITICAL, SEVERITY_HIGH, SEVERITY_MEDIUM,
    RULE_CRITICAL_BEFORE_IMPACT, RULE_HEALTH_TRACKED, RULE_ANOMALIES_DETECTED,
    RULE_ALERTS_ISSUED, RULE_SELF_VERIFICATION, RULE_QUALITY_PASS,
    ALL_QUALITY_RULES,
    VERDICT_READY, VERDICT_READY_WITH_WARNINGS, VERDICT_NOT_READY,
)


class QualityGate:
    def validate(
        self, report: SystemMonitoringReport
    ) -> Tuple[List[MonitoringFinding], bool, str]:
        findings: List[MonitoringFinding] = []
        critical_fail = False
        warnings = 0

        for rule in ALL_QUALITY_RULES:
            if rule == RULE_CRITICAL_BEFORE_IMPACT:
                # Critical alerts/anomalies must be present in the report
                # when problems exist — absence while health is low is failure
                if report.health.overall_score < 0.4 and report.critical_alert_count == 0:
                    findings.append(MonitoringFinding(
                        severity=SEVERITY_CRITICAL, code=rule,
                        message=(
                            "Critical system degradation without corresponding alerts."
                        ),
                        affected="alerts", category="detection",
                        resolution_hint="Ensure alert rules cover health collapse.",
                    ))
                    critical_fail = True
                elif report.critical_alert_count > 0:
                    findings.append(MonitoringFinding(
                        severity=SEVERITY_MEDIUM, code=rule,
                        message=(
                            f"{report.critical_alert_count} critical alert(s) raised "
                            "before impact propagation."
                        ),
                        affected="alerts", category="detection",
                    ))
                    warnings += 1

            elif rule == RULE_HEALTH_TRACKED:
                if report.health.overall_score <= 0 and report.engine_count > 0:
                    findings.append(MonitoringFinding(
                        severity=SEVERITY_HIGH, code=rule,
                        message="Health score not meaningfully tracked.",
                        affected="health", category="health",
                    ))
                    warnings += 1
                if report.engine_count > 0 and report.health.healthy_engines + report.health.unhealthy_engines == 0:
                    findings.append(MonitoringFinding(
                        severity=SEVERITY_CRITICAL, code=rule,
                        message="Engine health counts are zero despite engines present.",
                        affected="health", category="health",
                    ))
                    critical_fail = True

            elif rule == RULE_ANOMALIES_DETECTED:
                # If slow engines exist in performance but no anomalies → warn
                if report.performance.slow_engine_count > 0 and report.anomaly_count == 0:
                    findings.append(MonitoringFinding(
                        severity=SEVERITY_HIGH, code=rule,
                        message="Slow engines reported without anomaly records.",
                        affected="anomalies", category="anomaly",
                    ))
                    warnings += 1

            elif rule == RULE_ALERTS_ISSUED:
                failed = [
                    e for e in report.engine_statuses if e.state == "failed"
                ]
                if failed and not any(
                    a.kind == "engine_failure" for a in report.alerts
                ):
                    findings.append(MonitoringFinding(
                        severity=SEVERITY_CRITICAL, code=rule,
                        message="Failed engines present without engine_failure alerts.",
                        affected=",".join(e.engine_id for e in failed[:5]),
                        category="alerts",
                    ))
                    critical_fail = True

            elif rule == RULE_SELF_VERIFICATION:
                if not report.self_verification_passed:
                    findings.append(MonitoringFinding(
                        severity=SEVERITY_CRITICAL, code=rule,
                        message="Self-verification did not pass.",
                        affected="report", category="self_verification",
                    ))
                    critical_fail = True
                if not report.monitoring_self_ok:
                    findings.append(MonitoringFinding(
                        severity=SEVERITY_HIGH, code=rule,
                        message="Monitoring subsystem self-check failed.",
                        affected="monitor", category="self_verification",
                    ))
                    warnings += 1

            elif rule == RULE_QUALITY_PASS:
                if report.engine_count == 0:
                    findings.append(MonitoringFinding(
                        severity=SEVERITY_HIGH, code=rule,
                        message="No engines monitored.",
                        affected="engines", category="quality",
                    ))
                    warnings += 1
                if not report.metrics:
                    findings.append(MonitoringFinding(
                        severity=SEVERITY_CRITICAL, code=rule,
                        message="No metrics collected.",
                        affected="metrics", category="quality",
                    ))
                    critical_fail = True

        if critical_fail:
            return findings, False, VERDICT_NOT_READY
        if warnings > 0 or any(f.severity == SEVERITY_HIGH for f in findings):
            return findings, True, VERDICT_READY_WITH_WARNINGS
        return findings, True, VERDICT_READY


__all__ = ["QualityGate"]
