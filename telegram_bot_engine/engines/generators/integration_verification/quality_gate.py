"""QualityGate — Specification 042 (ULTRA CRITICAL)"""

from __future__ import annotations

from typing import List, Tuple

from .report_data import (
    IntegrationVerificationReport, IntegrationFinding,
    SEVERITY_CRITICAL, SEVERITY_HIGH, SEVERITY_MEDIUM,
    RULE_NO_INTEGRATION_FAILURE, RULE_INTERFACES_OK, RULE_DEPENDENCIES_OK,
    RULE_TELEGRAM_OK, RULE_DATA_FLOW_OK, RULE_SELF_VERIFICATION,
    RULE_QUALITY_PASS, RULE_SUFFICIENT_CONFIDENCE, ALL_QUALITY_RULES,
    MIN_INTEGRATION_SCORE, CONFIDENCE_MEDIUM_THRESHOLD,
    VERDICT_READY, VERDICT_READY_WITH_WARNINGS, VERDICT_NOT_READY,
    STATUS_FAILED,
    CHK_INTERFACE, CHK_DI, CHK_TG_STARTUP, CHK_DATA_FLOW,
)


class QualityGate:
    def validate(
        self, report: IntegrationVerificationReport
    ) -> Tuple[List[IntegrationFinding], bool, str]:
        findings: List[IntegrationFinding] = []
        critical_fail = False
        warnings = 0

        if report.is_empty and report.check_count == 0:
            findings.append(IntegrationFinding(
                severity=SEVERITY_MEDIUM, code="empty_report",
                message="Integration Verification Report has no checks.",
                affected="report", category="quality",
            ))
            warnings += 1

        failed = [c for c in report.checks if c.status == STATUS_FAILED]

        for rule in ALL_QUALITY_RULES:
            if rule == RULE_NO_INTEGRATION_FAILURE:
                crit = [c for c in failed if c.severity == SEVERITY_CRITICAL]
                if crit or (report.failed_count and any(
                    c.severity == SEVERITY_CRITICAL for c in failed
                )):
                    findings.append(IntegrationFinding(
                        severity=SEVERITY_CRITICAL, code=rule,
                        message=f"{len(crit) or report.failed_count} critical integration failure(s).",
                        affected="checks", category="integration",
                        resolution_hint="Fix integration failures before delivery.",
                    ))
                    critical_fail = True
                elif failed:
                    findings.append(IntegrationFinding(
                        severity=SEVERITY_HIGH, code=rule,
                        message=f"{len(failed)} integration failure(s).",
                        affected="checks", category="integration",
                    ))
                    # Spec: any integration problem blocks
                    critical_fail = True

            elif rule == RULE_INTERFACES_OK:
                bad = [
                    c for c in failed
                    if c.check_type == CHK_INTERFACE
                ]
                if bad:
                    findings.append(IntegrationFinding(
                        severity=SEVERITY_CRITICAL, code=rule,
                        message="Interface implementation checks failed.",
                        affected="interfaces", category="interfaces",
                    ))
                    critical_fail = True

            elif rule == RULE_DEPENDENCIES_OK:
                bad = [
                    c for c in failed
                    if c.check_type == CHK_DI
                ]
                unresolved = [d for d in report.dependencies if not d.resolved]
                if bad or unresolved:
                    findings.append(IntegrationFinding(
                        severity=SEVERITY_HIGH, code=rule,
                        message="Dependency resolution issues detected.",
                        affected="dependencies", category="dependencies",
                    ))
                    warnings += 1

            elif rule == RULE_TELEGRAM_OK:
                bad = [
                    c for c in failed
                    if c.check_type == CHK_TG_STARTUP
                ]
                if bad:
                    findings.append(IntegrationFinding(
                        severity=SEVERITY_CRITICAL, code=rule,
                        message="Telegram startup integration failed.",
                        affected="telegram", category="telegram",
                    ))
                    critical_fail = True

            elif rule == RULE_DATA_FLOW_OK:
                bad = [
                    c for c in failed
                    if c.check_type == CHK_DATA_FLOW
                ]
                if bad:
                    findings.append(IntegrationFinding(
                        severity=SEVERITY_CRITICAL, code=rule,
                        message="Cross-layer data flow verification failed.",
                        affected="data_flow", category="data_flow",
                    ))
                    critical_fail = True

            elif rule == RULE_SELF_VERIFICATION:
                if not report.self_verification_passed:
                    findings.append(IntegrationFinding(
                        severity=SEVERITY_CRITICAL, code=rule,
                        message="Self-verification did not pass.",
                        affected="report", category="self_verification",
                    ))
                    critical_fail = True

            elif rule == RULE_QUALITY_PASS:
                overall = report.score.overall if report.score else 0.0
                if overall < MIN_INTEGRATION_SCORE:
                    findings.append(IntegrationFinding(
                        severity=SEVERITY_HIGH, code=rule,
                        message=f"Integration score {overall:.1f} < {MIN_INTEGRATION_SCORE}.",
                        affected="score", category="quality",
                    ))
                    warnings += 1

            elif rule == RULE_SUFFICIENT_CONFIDENCE:
                conf = report.provenance.confidence if report.provenance else 0.0
                if conf < CONFIDENCE_MEDIUM_THRESHOLD:
                    findings.append(IntegrationFinding(
                        severity=SEVERITY_MEDIUM, code=rule,
                        message=f"Confidence {conf:.2f} below threshold.",
                        affected="provenance", category="confidence",
                    ))
                    warnings += 1

        if critical_fail:
            return findings, False, VERDICT_NOT_READY
        if warnings > 0 or any(f.severity == SEVERITY_HIGH for f in findings):
            return findings, True, VERDICT_READY_WITH_WARNINGS
        return findings, True, VERDICT_READY


__all__ = ["QualityGate"]
