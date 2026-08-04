"""
CentralLoggingEngine — Specification 058 (CRITICAL)

Single central log & audit sink for the platform. Collects events,
redacts secrets, seals immutable entries, supports search, rotation,
integrity verification. No engine may write logs outside this engine.
"""

from __future__ import annotations

import hashlib
import logging

from ....core.context import GenerationContext
from ....core.result import StageResult
from ...base.base_engine import BaseEngine
from .data_readers import (
    MonitoringReader, ResourceReader, SyncReader, OrchestratorReader,
    ExecutionContextReader, WorkspaceReader, UserRequestReader,
)
from .report_data import (
    CentralLoggingReport, ALL_SOURCES,
    SOURCE_MONITORING, SOURCE_RESOURCE, SOURCE_SYNC, SOURCE_ORCHESTRATOR,
    SOURCE_EXECUTION_CONTEXT, SOURCE_WORKSPACE, SOURCE_USER_REQUEST,
)
from .logger_core import CentralLogger
from .cache_manager import CacheManager
from .quality_gate import QualityGate
from .blueprint_builder import BlueprintBuilder

_log = logging.getLogger("engine.central_logging")


class CentralLoggingEngine(BaseEngine):
    """Specification 058 — Central Logging & Audit Engine."""

    def __init__(self) -> None:
        super().__init__(
            name="central_logging",
            version="1.0.0",
            description=(
                "Central logging and audit trail for the entire platform. "
                "Collects, redacts, seals (immutable), searches, rotates and "
                "verifies integrity of all logs. No engine may maintain a "
                "separate log store."
            ),
            tags=[
                "logging", "audit", "immutable", "security",
                "search", "rotation", "integrity",
            ],
            metadata={"specification": "058", "priority": "CRITICAL"},
        )
        self._mon_reader = MonitoringReader()
        self._res_reader = ResourceReader()
        self._sync_reader = SyncReader()
        self._orch_reader = OrchestratorReader()
        self._ctx_reader = ExecutionContextReader()
        self._ws_reader = WorkspaceReader()
        self._request_reader = UserRequestReader()
        self._logger = CentralLogger()
        self._cache = CacheManager(enabled=True)
        self._quality_gate = QualityGate()
        self._builder = BlueprintBuilder()

    def execute(self, context: GenerationContext) -> StageResult:
        try:
            _log.info("CentralLoggingEngine starting (Spec 058)")

            request_data = self._request_reader.read(context)
            mon_data = self._mon_reader.read(context)
            res_data = self._res_reader.read(context)
            sync_data = self._sync_reader.read(context)
            orch_data = self._orch_reader.read(context)
            ctx_data = self._ctx_reader.read(context)
            ws_data = self._ws_reader.read(context)

            sources_used = []
            sources_missing = []
            for key, data in (
                (SOURCE_USER_REQUEST, request_data),
                (SOURCE_MONITORING, mon_data),
                (SOURCE_RESOURCE, res_data),
                (SOURCE_SYNC, sync_data),
                (SOURCE_ORCHESTRATOR, orch_data),
                (SOURCE_EXECUTION_CONTEXT, ctx_data),
                (SOURCE_WORKSPACE, ws_data),
            ):
                if data.available:
                    sources_used.append(key)
                else:
                    sources_missing.append(key)

            cache_payload = str(sorted(sources_used)) + str(
                (mon_data.raw or {}).get("alert_count")
                or (request_data.raw or {}).get("project_id")
                or ""
            )
            cache_key = hashlib.sha256(cache_payload.encode("utf-8")).hexdigest()[:32]

            cached = self._cache.get(cache_key)
            if cached is not None:
                try:
                    report = CentralLoggingReport(**{
                        k: v for k, v in cached.items()
                        if k in CentralLoggingReport.__dataclass_fields__
                    })
                except Exception:
                    report = None
                if report is not None:
                    report.cache_info = self._cache.info_for_hit(cache_key)
                    context.set("central_logging_report", report)
                    return self.ok(
                        outputs={"central_logging_report": report.to_dict()},
                        metadata={"cache": "hit"},
                    )

            (
                entries, audit, search, integrity, archives,
                redacted, rotated, violations, mon_self_ok,
            ) = self._logger.process(
                mon_data, res_data, sync_data, orch_data,
                ctx_data, ws_data, request_data,
            )

            self_ok = self._logger.self_verify(
                entries, integrity, violations, mon_self_ok,
            )

            confidence = self._confidence(
                sources_used, sources_missing, entries, integrity, self_ok,
            )

            report = self._builder.build(
                entries=entries,
                audit_trail=audit,
                search=search,
                integrity=integrity,
                archives=archives,
                sources_used=sources_used,
                sources_missing=sources_missing,
                redacted_count=redacted,
                rotated=rotated,
                external_log_violations=violations,
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
            context.set("central_logging_report", report)

            _log.info(
                "CentralLoggingEngine finished — verdict=%s entries=%d "
                "audit=%d redacted=%d violations=%d",
                verdict, len(entries), len(audit), redacted, violations,
            )

            if not passed:
                return self.failed(
                    errors=[
                        f"Central Logging failed quality gate "
                        f"(verdict={verdict})"
                    ],
                    outputs={"central_logging_report": report_dict},
                    warnings=[f.message for f in gate_findings],
                )
            return self.ok(
                outputs={"central_logging_report": report_dict},
                metadata={
                    "report_id": report.report_id,
                    "verdict": verdict,
                    "entry_count": len(entries),
                    "audit_count": len(audit),
                    "redacted_count": redacted,
                    "rotated": rotated,
                    "external_log_violations": violations,
                    "integrity_verified": integrity.verified,
                    "self_verification_passed": self_ok,
                    "confidence": confidence,
                },
            )
        except Exception as exc:
            _log.exception("CentralLoggingEngine crashed: %s", exc)
            return self.failed(errors=[f"CentralLoggingEngine error: {exc}"])

    def _confidence(self, used, missing, entries, integrity, self_ok) -> float:
        total = len(ALL_SOURCES)
        ratio = len(used) / total if total else 0.0
        richness = min(1.0, len(entries) / 5.0)
        integ = 1.0 if integrity.verified else 0.3
        penalty = 0.0 if self_ok else 0.25
        conf = (0.25 * ratio) + (0.25 * richness) + (0.30 * integ) + 0.20 - penalty
        return round(max(0.0, min(1.0, conf)), 3)


__all__ = ["CentralLoggingEngine"]
