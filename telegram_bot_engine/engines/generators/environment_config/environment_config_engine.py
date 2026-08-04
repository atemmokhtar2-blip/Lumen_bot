"""
EnvironmentConfigEngine — Specification 051 (ULTRA CRITICAL)

Creates and validates Development/Testing/Staging/Production environments.
Secrets isolated (never in repo). Consistent behaviour across environments.
"""

from __future__ import annotations

import hashlib
import logging

from ....core.context import GenerationContext
from ....core.result import StageResult
from ...base.base_engine import BaseEngine
from .data_readers import (
    DependencyReader, WorkspaceReader, FileSystemReader,
    ProjectContextReader, UserRequestReader,
)
from .report_data import (
    EnvironmentConfigReport, ALL_SOURCES,
    SOURCE_DEPENDENCY, SOURCE_WORKSPACE, SOURCE_FILE_SYSTEM,
    SOURCE_PROJECT_CONTEXT, SOURCE_USER_REQUEST,
)
from .configurator import EnvironmentConfigurator
from .cache_manager import CacheManager
from .quality_gate import QualityGate
from .blueprint_builder import BlueprintBuilder

_log = logging.getLogger("engine.environment_config")


class EnvironmentConfigEngine(BaseEngine):
    """Specification 051 — Intelligent Environment Configuration Engine."""

    def __init__(self) -> None:
        super().__init__(
            name="environment_config",
            version="1.0.0",
            description=(
                "Builds Dev/Test/Staging/Production environments, manages .env "
                "templates, isolates secrets, validates consistency and health."
            ),
            tags=["environment", "config", "secrets", ".env", "health"],
            metadata={"specification": "051", "priority": "ULTRA_CRITICAL"},
        )
        self._dep_reader = DependencyReader()
        self._ws_reader = WorkspaceReader()
        self._fs_reader = FileSystemReader()
        self._ctx_reader = ProjectContextReader()
        self._request_reader = UserRequestReader()
        self._configurator = EnvironmentConfigurator()
        self._cache = CacheManager(enabled=True)
        self._quality_gate = QualityGate()
        self._builder = BlueprintBuilder()

    def execute(self, context: GenerationContext) -> StageResult:
        try:
            _log.info("EnvironmentConfigEngine starting (Spec 051)")

            request_data = self._request_reader.read(context)
            dep_data = self._dep_reader.read(context)
            ws_data = self._ws_reader.read(context)
            fs_data = self._fs_reader.read(context)
            ctx_data = self._ctx_reader.read(context)

            sources_used = []
            sources_missing = []
            for key, data in (
                (SOURCE_USER_REQUEST, request_data),
                (SOURCE_DEPENDENCY, dep_data),
                (SOURCE_WORKSPACE, ws_data),
                (SOURCE_FILE_SYSTEM, fs_data),
                (SOURCE_PROJECT_CONTEXT, ctx_data),
            ):
                if data.available:
                    sources_used.append(key)
                else:
                    sources_missing.append(key)

            cache_payload = str(sorted(sources_used)) + str(
                (request_data.raw or {}).get("environment")
                or (request_data.raw or {}).get("APP_ENV")
                or ""
            )
            cache_key = hashlib.sha256(cache_payload.encode("utf-8")).hexdigest()[:32]

            cached = self._cache.get(cache_key)
            if cached is not None:
                try:
                    report = EnvironmentConfigReport(**{
                        k: v for k, v in cached.items()
                        if k in EnvironmentConfigReport.__dataclass_fields__
                    })
                except Exception:
                    report = None
                if report is not None:
                    report.cache_info = self._cache.info_for_hit(cache_key)
                    context.set("environment_config_report", report)
                    return self.ok(
                        outputs={"environment_config_report": report.to_dict()},
                        metadata={"cache": "hit"},
                    )

            (
                profiles, variables, health_checks, backups, score,
                detected, secrets_isolated,
            ) = self._configurator.configure(
                request_data, ctx_data, dep_data, fs_data,
            )

            self_ok = self._configurator.self_verify(
                profiles, variables, secrets_isolated, score,
            )

            confidence = self._confidence(
                sources_used, sources_missing, score, secrets_isolated, self_ok,
            )

            report = self._builder.build(
                profiles=profiles,
                variables=variables,
                health_checks=health_checks,
                backups=backups,
                score=score,
                sources_used=sources_used,
                sources_missing=sources_missing,
                detected_environment=detected,
                secrets_isolated=secrets_isolated,
                self_verification_passed=self_ok,
                confidence=confidence,
            )

            gate_findings, passed, verdict = self._quality_gate.validate(report)
            report.findings.extend(gate_findings)
            report.verdict = verdict
            report.readiness_status = verdict
            report.self_verification_passed = self_ok
            report.secrets_isolated = secrets_isolated

            report_dict = report.to_dict()
            report.cache_info = self._cache.put(cache_key, report_dict)
            context.set("environment_config_report", report)

            _log.info(
                "EnvironmentConfigEngine finished — verdict=%s env=%s "
                "score=%.1f secrets_ok=%s",
                verdict, detected, score.overall, secrets_isolated,
            )

            if not passed:
                return self.failed(
                    errors=[
                        f"Environment Configuration failed quality gate "
                        f"(verdict={verdict})"
                    ],
                    outputs={"environment_config_report": report_dict},
                    warnings=[f.message for f in gate_findings],
                )
            return self.ok(
                outputs={"environment_config_report": report_dict},
                metadata={
                    "report_id": report.report_id,
                    "verdict": verdict,
                    "detected_environment": detected,
                    "profile_count": len(profiles),
                    "variable_count": len(variables),
                    "missing_count": report.missing_count,
                    "unsafe_count": report.unsafe_count,
                    "secrets_isolated": secrets_isolated,
                    "score_overall": score.overall,
                    "self_verification_passed": self_ok,
                    "confidence": confidence,
                },
            )
        except Exception as exc:
            _log.exception("EnvironmentConfigEngine crashed: %s", exc)
            return self.failed(errors=[f"EnvironmentConfigEngine error: {exc}"])

    def _confidence(
        self, used, missing, score, secrets_isolated, self_ok
    ) -> float:
        total = len(ALL_SOURCES)
        ratio = len(used) / total if total else 0.0
        score_f = (score.overall / 100.0) if score else 0.0
        penalty = (0.0 if secrets_isolated else 0.2) + (0.0 if self_ok else 0.2)
        conf = (0.30 * ratio) + (0.40 * score_f) + 0.30 - penalty
        return round(max(0.0, min(1.0, conf)), 3)


__all__ = ["EnvironmentConfigEngine"]
