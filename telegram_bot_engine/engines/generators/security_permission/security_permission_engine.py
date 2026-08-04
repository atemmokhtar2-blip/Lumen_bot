"""
SecurityPermissionEngine — Specification 060 (MAXIMUM CRITICAL)

Central security & permission management: roles, least privilege,
access validation, engine isolation, sensitive protection, internal
auth, audit and recovery. No engine may hold excess privileges.
"""

from __future__ import annotations

import hashlib
import logging

from ....core.context import GenerationContext
from ....core.result import StageResult
from ...base.base_engine import BaseEngine
from .data_readers import (
    ConfigReader, LoggingReader, MonitoringReader, ExecutionContextReader,
    WorkspaceReader, EcosystemReader, UserRequestReader,
)
from .report_data import (
    SecurityPermissionReport, ALL_SOURCES,
    SOURCE_CONFIG, SOURCE_LOGGING, SOURCE_MONITORING,
    SOURCE_EXECUTION_CONTEXT, SOURCE_WORKSPACE, SOURCE_ECOSYSTEM,
    SOURCE_USER_REQUEST,
)
from .security_manager import SecurityManager
from .cache_manager import CacheManager
from .quality_gate import QualityGate
from .blueprint_builder import BlueprintBuilder

_log = logging.getLogger("engine.security_permission")


class SecurityPermissionEngine(BaseEngine):
    """Specification 060 — Intelligent Security & Permission Management Engine."""

    def __init__(self) -> None:
        super().__init__(
            name="security_permission",
            version="1.0.0",
            description=(
                "Central security and permission management. Enforces least "
                "privilege, locked roles, access validation, engine isolation, "
                "sensitive resource protection, internal authentication, "
                "security audit and recovery on breach."
            ),
            tags=[
                "security", "permissions", "roles", "isolation",
                "auth", "audit", "least_privilege",
            ],
            metadata={"specification": "060", "priority": "MAXIMUM CRITICAL"},
        )
        self._config_reader = ConfigReader()
        self._log_reader = LoggingReader()
        self._mon_reader = MonitoringReader()
        self._ctx_reader = ExecutionContextReader()
        self._ws_reader = WorkspaceReader()
        self._eco_reader = EcosystemReader()
        self._request_reader = UserRequestReader()
        self._manager = SecurityManager()
        self._cache = CacheManager(enabled=True)
        self._quality_gate = QualityGate()
        self._builder = BlueprintBuilder()

    def execute(self, context: GenerationContext) -> StageResult:
        try:
            _log.info("SecurityPermissionEngine starting (Spec 060)")

            request_data = self._request_reader.read(context)
            config_data = self._config_reader.read(context)
            log_data = self._log_reader.read(context)
            mon_data = self._mon_reader.read(context)
            ctx_data = self._ctx_reader.read(context)
            ws_data = self._ws_reader.read(context)
            eco_data = self._eco_reader.read(context)

            sources_used = []
            sources_missing = []
            for key, data in (
                (SOURCE_USER_REQUEST, request_data),
                (SOURCE_CONFIG, config_data),
                (SOURCE_LOGGING, log_data),
                (SOURCE_MONITORING, mon_data),
                (SOURCE_EXECUTION_CONTEXT, ctx_data),
                (SOURCE_WORKSPACE, ws_data),
                (SOURCE_ECOSYSTEM, eco_data),
            ):
                if data.available:
                    sources_used.append(key)
                else:
                    sources_missing.append(key)

            cache_payload = str(sorted(sources_used)) + str(
                (eco_data.raw or {}).get("engine_count")
                or (request_data.raw or {}).get("project_id")
                or ""
            )
            cache_key = hashlib.sha256(cache_payload.encode("utf-8")).hexdigest()[:32]

            cached = self._cache.get(cache_key)
            if cached is not None:
                try:
                    report = SecurityPermissionReport(**{
                        k: v for k, v in cached.items()
                        if k in SecurityPermissionReport.__dataclass_fields__
                    })
                except Exception:
                    report = None
                if report is not None:
                    report.cache_info = self._cache.info_for_hit(cache_key)
                    context.set("security_permission_report", report)
                    return self.ok(
                        outputs={"security_permission_report": report.to_dict()},
                        metadata={"cache": "hit"},
                    )

            (
                grants, roles, checks, violations, auth, audit,
                recoveries, unauthorized, recovered, mon_self_ok,
            ) = self._manager.enforce(
                config_data, log_data, mon_data, ctx_data,
                ws_data, eco_data, request_data,
            )

            self_ok = self._manager.self_verify(
                roles, grants, checks, auth, unauthorized, mon_self_ok,
            )

            confidence = self._confidence(
                sources_used, sources_missing, roles, checks, self_ok,
            )

            report = self._builder.build(
                grants=grants,
                roles=roles,
                access_checks=checks,
                isolation_violations=violations,
                auth_records=auth,
                audit_trail=audit,
                recoveries=recoveries,
                sources_used=sources_used,
                sources_missing=sources_missing,
                unauthorized_attempts=unauthorized,
                recovered=recovered,
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
            context.set("security_permission_report", report)

            _log.info(
                "SecurityPermissionEngine finished — verdict=%s engines=%d "
                "denied=%d unauthorized=%d",
                verdict, len(roles), report.denied_count, unauthorized,
            )

            if not passed:
                return self.failed(
                    errors=[
                        f"Security & Permission failed quality gate "
                        f"(verdict={verdict})"
                    ],
                    outputs={"security_permission_report": report_dict},
                    warnings=[f.message for f in gate_findings],
                )
            return self.ok(
                outputs={"security_permission_report": report_dict},
                metadata={
                    "report_id": report.report_id,
                    "verdict": verdict,
                    "engine_count": len(roles),
                    "denied_count": report.denied_count,
                    "violation_count": report.violation_count,
                    "unauthorized_attempts": unauthorized,
                    "recovered": recovered,
                    "self_verification_passed": self_ok,
                    "confidence": confidence,
                },
            )
        except Exception as exc:
            _log.exception("SecurityPermissionEngine crashed: %s", exc)
            return self.failed(
                errors=[f"SecurityPermissionEngine error: {exc}"]
            )

    def _confidence(self, used, missing, roles, checks, self_ok) -> float:
        total = len(ALL_SOURCES)
        ratio = len(used) / total if total else 0.0
        richness = min(1.0, len(roles) / 5.0)
        validated = 1.0 if checks else 0.3
        penalty = 0.0 if self_ok else 0.25
        conf = (0.25 * ratio) + (0.25 * richness) + (0.30 * validated) + 0.20 - penalty
        return round(max(0.0, min(1.0, conf)), 3)


__all__ = ["SecurityPermissionEngine"]
