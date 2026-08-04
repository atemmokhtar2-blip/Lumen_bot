"""
EngineEcosystemEngine — Specification 052 (MAXIMUM CRITICAL)

Central heart of all engines. Registration required. Dependency graph,
capability discovery, compatibility, health monitoring, failure isolation.
"""

from __future__ import annotations

import hashlib
import logging

from ....core.context import GenerationContext
from ....core.result import StageResult
from ...base.base_engine import BaseEngine
from .data_readers import (
    EnvironmentReader, DependencyReader, WorkspaceReader,
    ProjectContextReader, UserRequestReader,
)
from .report_data import (
    EngineEcosystemReport, ALL_SOURCES,
    SOURCE_ENVIRONMENT, SOURCE_DEPENDENCY, SOURCE_WORKSPACE,
    SOURCE_PROJECT_CONTEXT, SOURCE_USER_REQUEST,
)
from .registry import EcosystemRegistry
from .cache_manager import CacheManager
from .quality_gate import QualityGate
from .blueprint_builder import BlueprintBuilder

_log = logging.getLogger("engine.engine_ecosystem")


class EngineEcosystemEngine(BaseEngine):
    """Specification 052 — Intelligent Engine Ecosystem & Registry Engine."""

    def __init__(self) -> None:
        super().__init__(
            name="engine_ecosystem",
            version="1.0.0",
            description=(
                "Central engine registry: manifests, capabilities, dependency graph, "
                "compatibility, service discovery, health monitoring and failure isolation."
            ),
            tags=["ecosystem", "registry", "discovery", "health", "isolation"],
            metadata={"specification": "052", "priority": "MAXIMUM_CRITICAL"},
        )
        self._env_reader = EnvironmentReader()
        self._dep_reader = DependencyReader()
        self._ws_reader = WorkspaceReader()
        self._ctx_reader = ProjectContextReader()
        self._request_reader = UserRequestReader()
        self._registry = EcosystemRegistry()
        self._cache = CacheManager(enabled=True)
        self._quality_gate = QualityGate()
        self._builder = BlueprintBuilder()

    def execute(self, context: GenerationContext) -> StageResult:
        try:
            _log.info("EngineEcosystemEngine starting (Spec 052)")

            request_data = self._request_reader.read(context)
            env_data = self._env_reader.read(context)
            dep_data = self._dep_reader.read(context)
            ws_data = self._ws_reader.read(context)
            ctx_data = self._ctx_reader.read(context)

            sources_used = []
            sources_missing = []
            for key, data in (
                (SOURCE_USER_REQUEST, request_data),
                (SOURCE_ENVIRONMENT, env_data),
                (SOURCE_DEPENDENCY, dep_data),
                (SOURCE_WORKSPACE, ws_data),
                (SOURCE_PROJECT_CONTEXT, ctx_data),
            ):
                if data.available:
                    sources_used.append(key)
                else:
                    sources_missing.append(key)

            cache_payload = str(sorted(sources_used)) + str(
                (request_data.raw or {}).get("engines") or ""
            )
            cache_key = hashlib.sha256(cache_payload.encode("utf-8")).hexdigest()[:32]

            cached = self._cache.get(cache_key)
            if cached is not None:
                try:
                    report = EngineEcosystemReport(**{
                        k: v for k, v in cached.items()
                        if k in EngineEcosystemReport.__dataclass_fields__
                    })
                except Exception:
                    report = None
                if report is not None:
                    report.cache_info = self._cache.info_for_hit(cache_key)
                    context.set("engine_ecosystem_report", report)
                    return self.ok(
                        outputs={"engine_ecosystem_report": report.to_dict()},
                        metadata={"cache": "hit"},
                    )

            manifests, edges, capabilities, compatibility, health = self._registry.build(
                request_data, ctx_data,
            )

            self_ok = self._registry.self_verify(
                manifests, edges, compatibility, health,
            )

            confidence = self._confidence(
                sources_used, sources_missing, manifests, compatibility, self_ok,
            )

            report = self._builder.build(
                manifests=manifests,
                edges=edges,
                capabilities=capabilities,
                compatibility=compatibility,
                health=health,
                sources_used=sources_used,
                sources_missing=sources_missing,
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
            context.set("engine_ecosystem_report", report)

            _log.info(
                "EngineEcosystemEngine finished — verdict=%s engines=%d "
                "conflicts=%d isolated=%d",
                verdict, len(manifests), report.conflict_count, report.isolated_count,
            )

            if not passed:
                return self.failed(
                    errors=[
                        f"Engine Ecosystem failed quality gate (verdict={verdict})"
                    ],
                    outputs={"engine_ecosystem_report": report_dict},
                    warnings=[f.message for f in gate_findings],
                )
            return self.ok(
                outputs={"engine_ecosystem_report": report_dict},
                metadata={
                    "report_id": report.report_id,
                    "verdict": verdict,
                    "engine_count": len(manifests),
                    "conflict_count": report.conflict_count,
                    "isolated_count": report.isolated_count,
                    "capability_count": len(capabilities),
                    "self_verification_passed": self_ok,
                    "confidence": confidence,
                },
            )
        except Exception as exc:
            _log.exception("EngineEcosystemEngine crashed: %s", exc)
            return self.failed(errors=[f"EngineEcosystemEngine error: {exc}"])

    def _confidence(self, used, missing, manifests, compatibility, self_ok) -> float:
        total = len(ALL_SOURCES)
        ratio = len(used) / total if total else 0.0
        richness = min(1.0, len(manifests) / 10.0)
        conflicts = sum(1 for c in compatibility if not c.compatible)
        penalty = min(0.4, conflicts * 0.1 + (0.0 if self_ok else 0.2))
        conf = (0.25 * ratio) + (0.40 * richness) + 0.35 - penalty
        return round(max(0.0, min(1.0, conf)), 3)


__all__ = ["EngineEcosystemEngine"]
