"""QualityGate — Specification 065."""

from __future__ import annotations

from typing import List, Tuple

from .report_data import (
    LiveDeploymentReport,
    DeploymentFinding,
    SEVERITY_CRITICAL,
    SEVERITY_HIGH,
    SEVERITY_MEDIUM,
    TEST_PASS,
    TEST_SKIP,
    DEPLOY_RUNNING,
    DEPLOY_FAILED,
    VERDICT_READY,
    VERDICT_READY_WITH_WARNINGS,
    VERDICT_NOT_READY,
    RULE_TOKEN_VALID,
    RULE_OWNERSHIP_OK,
    RULE_SECRETS_SAFE,
    RULE_DEPLOY_OK,
    RULE_HEALTH_OK,
    RULE_FUNCTIONAL_OK,
    RULE_NO_RUNTIME_ERRORS,
    MIN_QUALITY_SCORE,
)


class QualityGate:
    def validate(
        self, report: LiveDeploymentReport
    ) -> Tuple[List[DeploymentFinding], bool, str, float]:
        findings: List[DeploymentFinding] = []
        score = 0.0
        weights = {
            RULE_TOKEN_VALID: 0.20,
            RULE_OWNERSHIP_OK: 0.10,
            RULE_SECRETS_SAFE: 0.10,
            RULE_DEPLOY_OK: 0.20,
            RULE_HEALTH_OK: 0.15,
            RULE_FUNCTIONAL_OK: 0.15,
            RULE_NO_RUNTIME_ERRORS: 0.10,
        }
        earned = 0.0

        tv = report.token_validation
        if tv and tv.valid:
            earned += weights[RULE_TOKEN_VALID]
        else:
            findings.append(DeploymentFinding(
                severity=SEVERITY_CRITICAL,
                code=RULE_TOKEN_VALID,
                message="Bot token is missing or invalid.",
            ))

        if tv and tv.ownership_verified:
            earned += weights[RULE_OWNERSHIP_OK]
        else:
            findings.append(DeploymentFinding(
                severity=SEVERITY_HIGH,
                code=RULE_OWNERSHIP_OK,
                message="Token ownership was not verified for this session.",
            ))

        if report.secrets_stored:
            earned += weights[RULE_SECRETS_SAFE]
        else:
            findings.append(DeploymentFinding(
                severity=SEVERITY_HIGH,
                code=RULE_SECRETS_SAFE,
                message="Secrets were not stored via Secrets Manager.",
            ))

        dep = report.deployment
        if dep and dep.status == DEPLOY_RUNNING:
            earned += weights[RULE_DEPLOY_OK]
            if dep.dry_run:
                findings.append(DeploymentFinding(
                    severity=SEVERITY_MEDIUM,
                    code="deploy_dry_run",
                    message="Deployment completed in dry-run mode (no Railway token on platform).",
                ))
        elif dep and dep.status == DEPLOY_FAILED:
            findings.append(DeploymentFinding(
                severity=SEVERITY_CRITICAL,
                code=RULE_DEPLOY_OK,
                message=dep.message or "Deployment failed.",
            ))
        else:
            findings.append(DeploymentFinding(
                severity=SEVERITY_HIGH,
                code=RULE_DEPLOY_OK,
                message="Deployment did not reach running state.",
            ))

        health = report.health
        if health and health.online and health.telegram_reachable:
            earned += weights[RULE_HEALTH_OK]
        else:
            findings.append(DeploymentFinding(
                severity=SEVERITY_HIGH,
                code=RULE_HEALTH_OK,
                message="Health check did not confirm bot online.",
            ))

        functional_ok = False
        active = [t for t in report.functional_tests if t.status != TEST_SKIP]
        if active:
            functional_ok = all(t.status == TEST_PASS for t in active)
        if functional_ok:
            earned += weights[RULE_FUNCTIONAL_OK]
        elif active:
            findings.append(DeploymentFinding(
                severity=SEVERITY_HIGH,
                code=RULE_FUNCTIONAL_OK,
                message=f"Functional tests failed: {report.tests_failed}/{report.tests_total}.",
            ))
        else:
            findings.append(DeploymentFinding(
                severity=SEVERITY_MEDIUM,
                code=RULE_FUNCTIONAL_OK,
                message="No functional tests were executed.",
            ))

        if not report.runtime_errors:
            earned += weights[RULE_NO_RUNTIME_ERRORS]
        else:
            findings.append(DeploymentFinding(
                severity=SEVERITY_CRITICAL,
                code=RULE_NO_RUNTIME_ERRORS,
                message=f"{len(report.runtime_errors)} runtime error(s) detected.",
            ))

        score = round(earned, 3)
        critical = any(f.severity == SEVERITY_CRITICAL for f in findings)
        if critical or score < MIN_QUALITY_SCORE:
            verdict = VERDICT_NOT_READY
            passed = False
        elif findings:
            verdict = VERDICT_READY_WITH_WARNINGS
            passed = True
        else:
            verdict = VERDICT_READY
            passed = True

        return findings, passed, verdict, score
