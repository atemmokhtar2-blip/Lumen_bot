"""
ExecutionContextEngine — Specification 054 (CRITICAL)

Creates and manages the unified execution context shared by all engines.
One active context per project. Versioned, locked, validated and recoverable.
"""

from __future__ import annotations

import hashlib
import logging

from ....core.context import GenerationContext
from ....core.result import StageResult
from ...base.base_engine import BaseEngine
from .data_readers import (
    OrchestratorReader, EcosystemReader, WorkspaceReader,
    ProjectContextReader, UserRequestReader,
)
from .report_data import (
    ExecutionContextReport, ALL_SOURCES,
    SOURCE_ORCHESTRATOR, SOURCE_ECOSYSTEM, SOURCE_WORKSPACE,
    SOURCE_PROJECT_CONTEXT, SOURCE_USER_REQUEST,
)
from .context_manager import ContextManager
from .cache_manager import CacheManager
from .quality_gate import QualityGate
from .blueprint_builder import BlueprintBuilder

_log = logging.getLogger("engine.execution_context")


class ExecutionContextEngine(BaseEngine):
    """Specification 054 — Intelligent Execution Context Engine."""

    def __init__(self) -> None:
        super().__init__(
            name="execution_context",
            version="1.0.0",
            description=(
                "Unified execution context for all engines: shared state, "
                "versioning, locking, isolation, validation, sync and recovery. "
                "One active context per project."
            ),
            tags=["context", "shared-state", "versioning", "locking", "isolation"],
            metadata={"specification": "054", "priority": "CRITICAL"},
        )
        self._orch_reader = OrchestratorReader()
        self._eco_reader = EcosystemReader()
        self._ws_reader = WorkspaceReader()
        self._ctx_reader = ProjectContextReader()
        self._request_reader = UserRequestReader()
        self._manager = ContextManager()
        self._cache = CacheManager(enabled=True)
        self._quality_gate = QualityGate()
        self._builder = BlueprintBuilder()

    def execute(self, context: GenerationContext) -> StageResult:
        try:
            _log.info("ExecutionContextEngine starting (Spec 054)")

            request_data = self._request_reader.read(context)
            orch_data = self._orch_reader.read(context)
            eco_data = self._eco_reader.read(context)
            ws_data = self._ws_reader.read(context)
            ctx_data = self._ctx_reader.read(context)

            sources_used = []
            sources_missing = []
            for key, data in (
                (SOURCE_USER_REQUEST, request_data),
                (SOURCE_ORCHESTRATOR, orch_data),
                (SOURCE_ECOSYSTEM, eco_data),
                (SOURCE_WORKSPACE, ws_data),
                (SOURCE_PROJECT_CONTEXT, ctx_data),
            ):
                if data.available:
                    sources_used.append(key)
                else:
                    sources_missing.append(key)

            cache_payload = str(sorted(sources_used)) + str(
                (request_data.raw or {}).get("project_id")
                or (ws_data.raw or {}).get("project_id")
                or ""
            )
            cache_key = hashlib.sha256(cache_payload.encode("utf-8")).hexdigest()[:32]

            cached = self._cache.get(cache_key)
            if cached is not None:
                try:
                    report = ExecutionContextReport(**{
                        k: v for k, v in cached.items()
                        if k in ExecutionContextReport.__dataclass_fields__
                    })
                except Exception:
                    report = None
                if report is not None:
                    report.cache_info = self._cache.info_for_hit(cache_key)
                    context.set("execution_context_report", report)
                    return self.ok(
                        outputs={"execution_context_report": report.to_dict()},
                        metadata={"cache": "hit"},
                    )

            (
                context_id, project_id, status, version, versions, locks,
                changes, issues, shared_keys, active_count, isolated, recovered,
            ) = self._manager.manage(
                request_data, orch_data, eco_data, ws_data, ctx_data,
            )

            self_ok = self._manager.self_verify(
                context_id, project_id, active_count, isolated, issues,
            )

            confidence = self._confidence(
                sources_used, sources_missing, shared_keys, isolated, self_ok,
            )

            report = self._builder.build(
                context_id=context_id,
                project_id=project_id,
                status=status,
                version=version,
                versions=versions,
                locks=locks,
                changes=changes,
                validation_issues=issues,
                shared_keys=shared_keys,
                sources_used=sources_used,
                sources_missing=sources_missing,
                active_count=active_count,
                isolated=isolated,
                recovered=recovered,
                self_verification_passed=self_ok,
                confidence=confidence,
            )

            gate_findings, passed, verdict = self._quality_gate.validate(report)
            report.findings.extend(gate_findings)
            report.verdict = verdict
            report.readiness_status = verdict
            report.self_verification_passed = self_ok
            report.isolated = isolated
            report.recovered = recovered

            report_dict = report.to_dict()
            report.cache_info = self._cache.put(cache_key, report_dict)
            context.set("execution_context_report", report)
            # Also expose context id for downstream engines
            context.set("active_execution_context_id", context_id)

            _log.info(
                "ExecutionContextEngine finished — verdict=%s ctx=%s v=%d "
                "keys=%d isolated=%s",
                verdict, context_id[:12], version, len(shared_keys), isolated,
            )

            if not passed:
                return self.failed(
                    errors=[
                        f"Execution Context failed quality gate "
                        f"(verdict={verdict})"
                    ],
                    outputs={"execution_context_report": report_dict},
                    warnings=[f.message for f in gate_findings],
                )
            return self.ok(
                outputs={"execution_context_report": report_dict},
                metadata={
                    "report_id": report.report_id,
                    "verdict": verdict,
                    "context_id": context_id,
                    "project_id": project_id,
                    "version": version,
                    "shared_key_count": len(shared_keys),
                    "active_count": active_count,
                    "isolated": isolated,
                    "recovered": recovered,
                    "self_verification_passed": self_ok,
                    "confidence": confidence,
                },
            )
        except Exception as exc:
            _log.exception("ExecutionContextEngine crashed: %s", exc)
            return self.failed(errors=[f"ExecutionContextEngine error: {exc}"])

    def _confidence(
        self, used, missing, shared_keys, isolated, self_ok
    ) -> float:
        total = len(ALL_SOURCES)
        ratio = len(used) / total if total else 0.0
        richness = min(1.0, len(shared_keys) / 8.0)
        penalty = (0.0 if isolated else 0.2) + (0.0 if self_ok else 0.25)
        conf = (0.30 * ratio) + (0.30 * richness) + (0.40 if isolated else 0.1) - penalty
        return round(max(0.0, min(1.0, conf)), 3)


__all__ = ["ExecutionContextEngine"]
