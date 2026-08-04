"""QualityGate — Specification 045 (MAXIMUM CRITICAL)"""

from __future__ import annotations

from typing import List, Tuple

from .report_data import (
    ProductionReadinessReport, CertificationFinding,
    SEVERITY_CRITICAL, SEVERITY_HIGH, SEVERITY_MEDIUM,
    RULE_NO_CRITICAL, RULE_ALL_AXES_PASS, RULE_REGRESSION_CLEAN,
    RULE_TOKEN_GATE, RULE_SELF_VERIFICATION, RULE_CERTIFICATE_VALID,
    ALL_QUALITY_RULES, STATUS_FAIL,
    VERDICT_CERTIFIED, VERDICT_REJECTED, VERDICT_CONDITIONAL,
)


class QualityGate:
    def validate(
        self, report: ProductionReadinessReport
    ) -> Tuple[List[CertificationFinding], bool, str]:
        findings: List[CertificationFinding] = []
        critical_fail = False

        for rule in ALL_QUALITY_RULES:
            if rule == RULE_NO_CRITICAL:
                if report.blockers:
                    findings.append(CertificationFinding(
                        severity=SEVERITY_CRITICAL, code=rule,
                        message=f"{len(report.blockers)} critical blocker(s) present.",
                        affected="blockers", category="certification",
                        resolution_hint="Clear all critical blockers before certification.",
                    ))
                    critical_fail = True

            elif rule == RULE_ALL_AXES_PASS:
                failed = [a for a in report.axes if a.status == STATUS_FAIL]
                if failed:
                    findings.append(CertificationFinding(
                        severity=SEVERITY_CRITICAL, code=rule,
                        message=(
                            "Axes below threshold: "
                            + ", ".join(f"{a.axis}={a.score:.1f}" for a in failed)
                        ),
                        affected="axes", category="scoring",
                        resolution_hint="Raise scores via responsible engines.",
                    ))
                    critical_fail = True

            elif rule == RULE_REGRESSION_CLEAN:
                # Informed by self-healing / e2e residual failures already in blockers
                pass

            elif rule == RULE_TOKEN_GATE:
                if report.certified and not report.token_gate_open:
                    findings.append(CertificationFinding(
                        severity=SEVERITY_CRITICAL, code=rule,
                        message="Certified but token gate closed — inconsistent state.",
                        affected="token_gate", category="gate",
                    ))
                    critical_fail = True
                if not report.certified and report.token_gate_open:
                    findings.append(CertificationFinding(
                        severity=SEVERITY_CRITICAL, code=rule,
                        message="Token gate open without certificate — FORBIDDEN.",
                        affected="token_gate", category="gate",
                        resolution_hint="Token gate must stay closed until certified.",
                    ))
                    critical_fail = True

            elif rule == RULE_SELF_VERIFICATION:
                if not report.self_verification_passed:
                    findings.append(CertificationFinding(
                        severity=SEVERITY_CRITICAL, code=rule,
                        message="Self-verification did not pass.",
                        affected="report", category="self_verification",
                    ))
                    critical_fail = True

            elif rule == RULE_CERTIFICATE_VALID:
                if report.certified and not (
                    report.certificate and report.certificate.issued
                ):
                    findings.append(CertificationFinding(
                        severity=SEVERITY_CRITICAL, code=rule,
                        message="Certified flag set but certificate not issued.",
                        affected="certificate", category="certificate",
                    ))
                    critical_fail = True

        if critical_fail or not report.certified:
            # Rejection is an expected valid outcome — gate "passes" structurally
            # but verdict stays rejected; engine.execute will still surface rejection.
            if not report.certified:
                return findings, False, VERDICT_REJECTED
            return findings, False, VERDICT_REJECTED

        return findings, True, VERDICT_CERTIFIED


__all__ = ["QualityGate"]
