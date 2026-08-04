"""
SynchronizationEngine — Specification 055 (CRITICAL)

Synchronizes all system states so every engine sees the same data.
Conflict detection/resolution, atomic transactions, recovery, health metrics.
"""

from __future__ import annotations

import hashlib
import logging

from ....core.context import GenerationContext
from ....core.result import StageResult
from ...base.base_engine import BaseEngine
from .data_readers import (
    ExecutionContextReader, OrchestratorReader, EcosystemReader,
    WorkspaceReader, UserRequestReader,
)
from .report_data import (
    SynchronizationReport, ALL_SOURCES,
    SOURCE_EXECUTION_CONTEXT, SOURCE_ORCHESTRATOR, SOURCE_ECOSYSTEM,
    SOURCE_WORKSPACE, SOURCE_USER_REQUEST,
)
from .synchronizer import Synchronizer
from .cache_manager import CacheManager
from .quality_gate import QualityGate
from .blueprint_builder import BlueprintBuilder

_log = logging.getLogger("engine.synchronization")


class SynchronizationEngine(BaseEngine):
    """Specification 055 — Intelligent Synchronization Engine."""

    def __init__(self) -> None:
        super().__init__(
            name="synchronization",
            version="1.0.0",
            description=(
                "Synchronizes project/execution/workspace/engine state across all "
                "engines. Detects and resolves conflicts without data loss. "
                "Atomic transactions, recovery and consistency verification."
            ),
            tags=["sync", "consistency", "conflict", "atomic", "realtime"],
            metadata={"specification": "055", "priority": "CRITICAL"},
        )
        self._ctx_reader = ExecutionContextReader()
        self._orch_reader = OrchestratorReader()
        self._eco_reader = EcosystemReader()
        self._ws_reader = WorkspaceReader()
        self._request_reader = UserRequestReader()
        self._sync = Synchronizer()
        self._cache = CacheManager(enabled=True)
        self._quality_gate = QualityGate()
        self._builder = BlueprintBuilder()

    def execute(self, context: GenerationContext) -> StageResult:
        try:
            _log.info("SynchronizationEngine starting (Spec 055)")

            request_data = self._request_reader.read(context)
            ctx_data = self._ctx_reader.read(context)
            orch_data = self._orch_reader.read(context)
            eco_data = self._eco_reader.read(context)
            ws_data = self._ws_reader.read(context)

            sources_used = []
            sources_missing = []
            for key, data in (
                (SOURCE_USER_REQUEST, request_data),
                (SOURCE_EXECUTION_CONTEXT, ctx_data),
                (SOURCE_ORCHESTRATOR, orch_data),
                (SOURCE_ECOSYSTEM, eco_data),
                (SOURCE_WORKSPACE, ws_data),
            ):
                if data.available:
                    sources_used.append(key)
                else:
                    sources_missing.append(key)

            cache_payload = str(sorted(sources_used)) + str(
                (ctx_data.raw or {}).get("version")
                or (ctx_data.raw or {}).get("context_id")
                or ""
            )
            cache_key = hashlib.sha256(cache_payload.encode("utf-8")).hexdigest()[:32]

            cached = self._cache.get(cache_key)
            if cached is not None:
                try:
                    report = SynchronizationReport(**{
                        k: v for k, v in cached.items()
                        if k in SynchronizationReport.__dataclass_fields__
                    })
                except Exception:
                    report = None
                if report is not None:
                    report.cache_info = self._cache.info_for_hit(cache_key)
                    context.set("synchronization_report", report)
                    return self.ok(
                        outputs={"synchronization_report": report.to_dict()},
                        metadata={"cache": "hit"},
                    )

            (
                events, conflicts, transactions, health, recovered, consistent,
            ) = self._sync.synchronize(
                request_data, ctx_data, orch_data, eco_data, ws_data,
            )

            self_ok = self._sync.self_verify(
                events, conflicts, transactions, consistent,
            )

            confidence = self._confidence(
                sources_used, sources_missing, events, consistent, self_ok,
            )

            report = self._builder.build(
                events=events, conflicts=conflicts, transactions=transactions,
                health=health, sources_used=sources_used,
                sources_missing=sources_missing, recovered=recovered,
                consistent=consistent, self_verification_passed=self_ok,
                confidence=confidence,
            )

            gate_findings, passed, verdict = self._quality_gate.validate(report)
            report.findings.extend(gate_findings)
            report.verdict = verdict
            report.readiness_status = verdict
            report.self_verification_passed = self_ok
            report.consistent = consistent
            report.recovered = recovered

            report_dict = report.to_dict()
            report.cache_info = self._cache.put(cache_key, report_dict)
            context.set("synchronization_report", report)

            _log.info(
                "SynchronizationEngine finished — verdict=%s events=%d "
                "conflicts=%d consistent=%s",
                verdict, len(events), len(conflicts), consistent,
            )

            if not passed:
                return self.failed(
                    errors=[f"Synchronization failed quality gate (verdict={verdict})"],
                    outputs={"synchronization_report": report_dict},
                    warnings=[f.message for f in gate_findings],
                )
            return self.ok(
                outputs={"synchronization_report": report_dict},
                metadata={
                    "report_id": report.report_id,
                    "verdict": verdict,
                    "event_count": len(events),
                    "conflict_count": len(conflicts),
                    "unresolved_count": report.unresolved_count,
                    "consistent": consistent,
                    "recovered": recovered,
                    "consistency_rate": health.consistency_rate,
                    "self_verification_passed": self_ok,
                    "confidence": confidence,
                },
            )
        except Exception as exc:
            _log.exception("SynchronizationEngine crashed: %s", exc)
            return self.failed(errors=[f"SynchronizationEngine error: {exc}"])

    def _confidence(self, used, missing, events, consistent, self_ok) -> float:
        total = len(ALL_SOURCES)
        ratio = len(used) / total if total else 0.0
        richness = min(1.0, len(events) / 5.0)
        penalty = (0.0 if consistent else 0.2) + (0.0 if self_ok else 0.25)
        conf = (0.30 * ratio) + (0.30 * richness) + (0.40 if consistent else 0.1) - penalty
        return round(max(0.0, min(1.0, conf)), 3)


__all__ = ["SynchronizationEngine"]
