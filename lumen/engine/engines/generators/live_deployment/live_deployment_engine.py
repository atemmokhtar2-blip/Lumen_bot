"""
LiveDeploymentEngine — Specification 065 (MAXIMUM CRITICAL)

Live Deployment & Smart Testing Engine.

Runs AFTER successful project generation when the user provides a
Telegram Bot Token. Validates token, stores secrets, writes .env,
deploys via DeploymentProvider (Railway driver), health-checks,
runs functional tests, and produces a full report.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

from ....core.context import GenerationContext
from ....core.result import StageResult
from ...base.base_engine import BaseEngine
from .blueprint_builder import BlueprintBuilder
from .cache_manager import CacheManager
from .data_readers import ProjectOutputReader, MaterializeReader, ProductionReadinessReader
from .environment_generator import EnvironmentGenerator
from .functional_tester import FunctionalTester
from .health_checker import HealthChecker
from .quality_gate import QualityGate
from .local_process_driver import LocalProcessDriver
from .docker_process_driver import DockerProcessDriver, docker_available
from .railway_driver import RailwayDriver
from .report_data import (
    LiveDeploymentReport,
    RuntimeErrorRecord,
    DEPLOY_RUNNING,
    MAX_REPAIR_ATTEMPTS,
)
from .secrets_manager import SecretsManager, get_secrets_manager
from .token_validator import TokenValidator

_log = logging.getLogger("engine.live_deployment")


def _select_primary_provider():
    """Production path: sandbox_runtime only (Firecracker; weak backends are dev-only)."""
    from lumen.engine.engines.generators.live_deployment.sandbox_process_driver import (
        SandboxProcessDriver,
    )
    from lumen.engine.services.isolation_policy import decide_isolation, require_strong_isolation

    decision = decide_isolation()
    if decision.require_strong_isolation:
        require_strong_isolation()
    driver = SandboxProcessDriver()
    _log.info("Live deployment provider=%s (%s)", driver.name, decision.reason)
    return driver


class LiveDeploymentEngine(BaseEngine):
    """Specification 065 — Live Deployment & Smart Testing Engine."""

    def __init__(self) -> None:
        super().__init__(
            name="live_deployment",
            version="1.1.0",
            description=(
                "Installs dependencies, runs the generated bot in an isolated "
                "sandbox (Firecracker in production), validates the "
                "Telegram token, health-checks, runs functional tests. "
                "Railway remains an optional provider."
            ),
            tags=[
                "deployment", "docker", "local-process", "railway", "token",
                "health", "testing", "secrets", "live", "maximum-critical",
            ],
            metadata={"specification": "065", "priority": "MAXIMUM CRITICAL"},
        )
        self._token_validator = TokenValidator()
        self._secrets = get_secrets_manager()
        self._env_gen = EnvironmentGenerator()
        # Strong isolation only via sandbox_runtime
        self._provider = _select_primary_provider()
        self._railway = RailwayDriver()
        self._health = HealthChecker()
        self._functional = FunctionalTester()
        self._quality = QualityGate()
        self._cache = CacheManager()
        self._blueprint = BlueprintBuilder()
        self._project_reader = ProjectOutputReader()
        self._materialize_reader = MaterializeReader()
        self._prod_reader = ProductionReadinessReader()

    # ------------------------------------------------------------------
    # Pipeline entry (optional — mainly driven from Telegram UI)
    # ------------------------------------------------------------------

    def execute(self, context: GenerationContext) -> StageResult:
        """
        If context already has a token secret id and project path, run
        the full live deployment flow. Otherwise return a pending report
        explaining that a token is required.
        """
        try:
            project_path = self._resolve_project_path(context)
            token = context.get("live_bot_token")  # never logged
            owner_id = context.get("live_owner_user_id")
            expected_reply = None
            mat = self._materialize_reader.read(context)
            if mat.available and mat.items:
                expected_reply = mat.items[0].get("start_reply")

            if not project_path:
                report = self._blueprint.build_empty()
                report.findings = []
                context.set("live_deployment_report", report)
                return self.failed(
                    errors=["No project_path available for live deployment."],
                    outputs={"live_deployment_report": report.to_dict()},
                )

            if not token:
                report = self._blueprint.build_empty(project_path)
                context.set("live_deployment_report", report)
                return self.ok(
                    outputs={
                        "live_deployment_report": report.to_dict(),
                        "awaiting_token": True,
                        "message": (
                            "Project ready. Send a Telegram Bot Token to "
                            "start live deployment."
                        ),
                    },
                    metadata={"awaiting_token": True},
                )

            report = self.run_live_deployment(
                project_path=project_path,
                bot_token=token,
                owner_user_id=owner_id,
                expected_start_reply=expected_reply,
            )
            context.set("live_deployment_report", report)
            # Clear token from context artefacts immediately
            try:
                context.artefacts.pop("live_bot_token", None)
            except Exception:
                pass

            if report.passed:
                return self.ok(
                    outputs={"live_deployment_report": report.to_dict()},
                    metadata={"verdict": report.verdict, "score": report.quality_score},
                )
            return self.failed(
                errors=[f"Live deployment not ready (verdict={report.verdict})"],
                outputs={"live_deployment_report": report.to_dict()},
                warnings=[f.message for f in report.findings[:5]],
            )
        except Exception as e:
            _log.exception("LiveDeploymentEngine crashed")
            return self.failed(errors=[f"LiveDeploymentEngine error: {type(e).__name__}"])

    # ------------------------------------------------------------------
    # Public API used by Telegram bot layer
    # ------------------------------------------------------------------

    def run_live_deployment(
        self,
        *,
        project_path: str,
        bot_token: str,
        owner_user_id: Optional[int] = None,
        expected_start_reply: Optional[str] = None,
        repair_attempt: int = 0,
    ) -> LiveDeploymentReport:
        report = self._blueprint.build_empty(project_path)
        report.repair_attempts = repair_attempt
        report.max_repair_attempts = MAX_REPAIR_ATTEMPTS
        secret_id = f"bot_token_{owner_user_id or 'anon'}_{Path(project_path).name}"

        # 1) Token validation
        tv = self._token_validator.validate(
            bot_token,
            expected_owner_user_id=owner_user_id,
        )
        report.token_validation = tv
        if not tv.valid:
            report.verdict = "not_ready"
            report.passed = False
            findings, _, verdict, score = self._quality.validate(report)
            report.findings = findings
            report.quality_score = score
            report.verdict = verdict
            return report

        # 2) Secrets — put(value, secret_id=...) so the token is retrievable
        #    later by restart_by_project using the same secret_id
        self._secrets.put(bot_token, secret_id=secret_id)
        report.secrets_stored = True

        # 3) Environment (.env) — token only on disk in .env, never logged
        report.env_written = self._env_gen.write_env(
            project_path,
            bot_token=bot_token,
        )

        # 4) REAL deploy: pip install + start bot process (never log token)
        try:
            deployment = self._provider.deploy(
                project_path,
                env_vars={"BOT_TOKEN": bot_token},
                service_name=Path(project_path).name[:40] or "generated-bot",
            )
            report.deployment = deployment
            # Give polling a moment to connect to Telegram
            if deployment.status == DEPLOY_RUNNING:
                import time
                time.sleep(2.5)
        except Exception as e:
            report.runtime_errors.append(RuntimeErrorRecord(
                error_type=type(e).__name__,
                message=str(e)[:300],
                engine="live_deployment",
            ))

        # 5) Health
        try:
            report.health = self._health.check(self._secrets, secret_id)
        except Exception as e:
            report.runtime_errors.append(RuntimeErrorRecord(
                error_type=type(e).__name__,
                message=f"Health check: {e}"[:300],
                engine="live_deployment.health",
            ))

        # 6) Functional tests
        try:
            report.functional_tests = self._functional.run(
                project_path,
                self._secrets,
                secret_id,
                expected_start_reply=expected_start_reply,
            )
        except Exception as e:
            report.runtime_errors.append(RuntimeErrorRecord(
                error_type=type(e).__name__,
                message=f"Functional tests: {e}"[:300],
                engine="live_deployment.functional",
            ))

        # 7) Logs (redacted)
        if report.deployment and report.deployment.deployment_id:
            try:
                raw_logs = self._provider.logs(report.deployment.deployment_id, limit=40)
                report.logs_tail = [
                    self._secrets.redact(line, secret_id) for line in raw_logs
                ]
            except Exception:
                report.logs_tail = []

        # 8) Quality gate
        findings, passed, verdict, score = self._quality.validate(report)
        report.findings = findings
        report.passed = passed
        report.verdict = verdict
        report.quality_score = score

        _log.info(
            "Live deployment finished",
            extra={
                "passed": report.passed,
                "verdict": report.verdict,
                "score": report.quality_score,
                "dry_run": bool(report.deployment and report.deployment.dry_run),
            },
        )
        return report

    def stop_deployment(self, deployment_id: str) -> Dict[str, Any]:
        st = self._provider.stop(deployment_id)
        return st.to_dict()

    def restart_deployment(self, deployment_id: str) -> Dict[str, Any]:
        st = self._provider.restart(deployment_id)
        return st.to_dict()

    def restart_by_project(
        self,
        project_path: str,
        *,
        owner_user_id: Optional[int] = None,
    ) -> Dict[str, Any]:
        """Smart restart after a repo edit: kill every running deployment for
        this project_path and start a fresh one with the *same* token so the
        edited code runs immediately.

        This is the orchestration the router calls after a successful edit:
          1. compute the secret_id the same way run_live_deployment does
          2. retrieve the sealed bot token from SecretsManager
          3. find all deployments for this project via the deployment registry
          4. for each RUNNING one: provider.restart(dep, token, path)
          5. if none were running, deploy a brand-new one (edit-then-run)

        Returns a summary dict: {restarted, deployed, errors, details}.
        """
        result: Dict[str, Any] = {
            "project_path": str(project_path),
            "restarted": 0,
            "deployed": 0,
            "errors": [],
            "details": [],
        }
        try:
            p = Path(project_path)
            project_name = p.name
        except Exception:
            project_name = str(project_path)
        secret_id = f"bot_token_{owner_user_id or 'anon'}_{project_name}"
        bot_token = self._secrets.get(secret_id) or ""

        # find all deployments for this project path
        try:
            from lumen.engine.services.deployment_registry import (
                get_deployment_registry,
            )
            registry = get_deployment_registry()
            records = registry.by_project(str(project_path)) or []
        except Exception:
            records = []

        running_ids = [
            (r.get("deployment_id") or "")
            for r in records
            if str(r.get("status") or "").lower() == "running"
        ]

        if running_ids and bot_token:
            for dep_id in running_ids:
                try:
                    st = self._provider.restart(
                        dep_id,
                        bot_token=bot_token,
                        project_path=str(project_path),
                    )
                    d = st.to_dict()
                    result["details"].append(d)
                    if st.status == DEPLOY_RUNNING:
                        result["restarted"] += 1
                    else:
                        result["errors"].append(
                            f"{dep_id}: {st.status} {st.message}"
                        )
                except Exception as e:
                    result["errors"].append(f"{dep_id}: {type(e).__name__}: {e}")
        elif bot_token:
            # no running deployment found → deploy a fresh one
            try:
                st = self._provider.deploy(
                    str(project_path),
                    env_vars={"BOT_TOKEN": bot_token},
                    service_name=project_name[:40] or "generated-bot",
                )
                result["details"].append(st.to_dict())
                if st.status == DEPLOY_RUNNING:
                    result["deployed"] += 1
                else:
                    result["errors"].append(f"deploy: {st.status} {st.message}")
            except Exception as e:
                result["errors"].append(f"deploy: {type(e).__name__}: {e}")
        else:
            result["errors"].append(
                "no_bot_token: secret not found (bot was never deployed live, "
                "or process restarted since). Nothing to restart."
            )

        _log.info(
            "restart_by_project path=%s restarted=%d deployed=%d errors=%d",
            project_path, result["restarted"], result["deployed"],
            len(result["errors"]),
        )
        return result

    def get_logs(self, deployment_id: str, secret_id: Optional[str] = None) -> List[str]:
        lines = self._provider.logs(deployment_id)
        if secret_id:
            lines = [self._secrets.redact(l, secret_id) for l in lines]
        return lines

    def _resolve_project_path(self, context: GenerationContext) -> str:
        if context.work_dir and Path(context.work_dir).exists():
            # Prefer work_dir if it already has main.py
            wd = Path(context.work_dir)
            if (wd / "main.py").exists() or any(wd.rglob("main.py")):
                return str(wd)
        proj = context.get("final_project") or {}
        if isinstance(proj, dict) and proj.get("project_path"):
            return str(proj["project_path"])
        return str(context.work_dir) if context.work_dir else ""
