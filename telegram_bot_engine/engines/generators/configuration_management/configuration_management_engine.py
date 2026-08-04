"""
ConfigurationManagementEngine — Specification 059 (CRITICAL)

Central configuration registry for the platform and all engines.
Validation, defaults, dynamic updates, versioning, rollback, sync,
protection, backup and recovery. No engine may keep config outside.
"""

from __future__ import annotations

import hashlib
import logging

from ....core.context import GenerationContext
from ....core.result import StageResult
from ...base.base_engine import BaseEngine
from .data_readers import (
    LoggingReader, MonitoringReader, ResourceReader,
    EnvironmentReader, WorkspaceReader, UserRequestReader,
)
from .report_data import (
    ConfigurationManagementReport, ALL_SOURCES,
    SOURCE_LOGGING, SOURCE_MONITORING, SOURCE_RESOURCE,
    SOURCE_ENV, SOURCE_WORKSPACE, SOURCE_USER_REQUEST,
)
from .config_manager import ConfigManager
from .cache_manager import CacheManager
from .quality_gate import QualityGate
from .blueprint_builder import BlueprintBuilder

_log = logging.getLogger("engine.configuration_management")


class ConfigurationManagementEngine(BaseEngine):
    """Specification 059 — Intelligent Configuration Management Engine."""

    def __init__(self) -> None:
        super().__init__(
            name="configuration_management",
            version="1.0.0",
            description=(
                "Central configuration management for the platform and all engines. "
                "Registry, validation, defaults, dynamic updates, versioning, "
                "rollback, synchronization, protection, backup and recovery. "
                "No engine may retain configuration outside this engine."
            ),
            tags=[
                "configuration", "registry", "validation", "versioning",
                "rollback", "backup", "protection",
            ],
            metadata={"specification": "059", "priority": "CRITICAL"},
        )
        self._log_reader = LoggingReader()
        self._mon_reader = MonitoringReader()
        self._res_reader = ResourceReader()
        self._env_reader = EnvironmentReader()
        self._ws_reader = WorkspaceReader()
        self._request_reader = UserRequestReader()
        self._manager = ConfigManager()
        self._cache = CacheManager(enabled=True)
        self._quality_gate = QualityGate()
        self._builder = BlueprintBuilder()

    def execute(self, context: GenerationContext) -> StageResult:
        try:
            _log.info("ConfigurationManagementEngine starting (Spec 059)")

            request_data = self._request_reader.read(context)
            log_data = self._log_reader.read(context)
            mon_data = self._mon_reader.read(context)
            res_data = self._res_reader.read(context)
            env_data = self._env_reader.read(context)
            ws_data = self._ws_reader.read(context)

            sources_used = []
            sources_missing = []
            for key, data in (
                (SOURCE_USER_REQUEST, request_data),
                (SOURCE_LOGGING, log_data),
                (SOURCE_MONITORING, mon_data),
                (SOURCE_RESOURCE, res_data),
                (SOURCE_ENV, env_data),
                (SOURCE_WORKSPACE, ws_data),
            ):
                if data.available:
                    sources_used.append(key)
                else:
                    sources_missing.append(key)

            cache_payload = str(sorted(sources_used)) + str(
                (request_data.raw or {}).get("project_id")
                or (env_data.raw or {}).get("env_count")
                or ""
            )
            cache_key = hashlib.sha256(cache_payload.encode("utf-8")).hexdigest()[:32]

            cached = self._cache.get(cache_key)
            if cached is not None:
                try:
                    report = ConfigurationManagementReport(**{
                        k: v for k, v in cached.items()
                        if k in ConfigurationManagementReport.__dataclass_fields__
                    })
                except Exception:
                    report = None
                if report is not None:
                    report.cache_info = self._cache.info_for_hit(cache_key)
                    context.set("configuration_management_report", report)
                    return self.ok(
                        outputs={"configuration_management_report": report.to_dict()},
                        metadata={"cache": "hit"},
                    )

            (
                entries, issues, versions, backups, recoveries, change_log,
                current_version, synced, violations, protected, mon_self_ok,
            ) = self._manager.manage(
                log_data, mon_data, res_data, env_data, ws_data, request_data,
            )

            self_ok = self._manager.self_verify(
                entries, issues, violations, mon_self_ok,
            )

            confidence = self._confidence(
                sources_used, sources_missing, entries, issues, self_ok,
            )

            report = self._builder.build(
                entries=entries,
                issues=issues,
                versions=versions,
                backups=backups,
                recoveries=recoveries,
                change_log=change_log,
                sources_used=sources_used,
                sources_missing=sources_missing,
                current_version=current_version,
                synced=synced,
                external_config_violations=violations,
                protected_keys=protected,
                self_verification_passed=self_ok,
                confidence=confidence,
            )

            gate_findings, passed, verdict = self._quality_gate.validate(report)
            report.findings.extend(gate_findings)
            report.verdict = verdict
            report.readiness_status = verdict
            report.self_verification_passed = self_ok

            report_dict = report.to_dict()
            report.cache_info = self._cache.put(cache_key, report_dict)
            context.set("configuration_management_report", report)

            _log.info(
                "ConfigurationManagementEngine finished — verdict=%s entries=%d "
                "issues=%d version=%d",
                verdict, len(entries), len(issues), current_version,
            )

            if not passed:
                return self.failed(
                    errors=[
                        f"Configuration Management failed quality gate "
                        f"(verdict={verdict})"
                    ],
                    outputs={"configuration_management_report": report_dict},
                    warnings=[f.message for f in gate_findings],
                )
            return self.ok(
                outputs={"configuration_management_report": report_dict},
                metadata={
                    "report_id": report.report_id,
                    "verdict": verdict,
                    "entry_count": len(entries),
                    "issue_count": len(issues),
                    "current_version": current_version,
                    "synced": synced,
                    "protected_keys": protected,
                    "external_config_violations": violations,
                    "self_verification_passed": self_ok,
                    "confidence": confidence,
                },
            )
        except Exception as exc:
            _log.exception("ConfigurationManagementEngine crashed: %s", exc)
            return self.failed(
                errors=[f"ConfigurationManagementEngine error: {exc}"]
            )

    def _confidence(self, used, missing, entries, issues, self_ok) -> float:
        total = len(ALL_SOURCES)
        ratio = len(used) / total if total else 0.0
        richness = min(1.0, len(entries) / 10.0)
        clean = 1.0 if not issues else max(0.2, 1.0 - 0.1 * len(issues))
        penalty = 0.0 if self_ok else 0.25
        conf = (0.25 * ratio) + (0.25 * richness) + (0.30 * clean) + 0.20 - penalty
        return round(max(0.0, min(1.0, conf)), 3)


__all__ = ["ConfigurationManagementEngine"]
