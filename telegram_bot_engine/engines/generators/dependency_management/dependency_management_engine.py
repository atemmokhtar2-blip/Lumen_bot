"""
DependencyManagementEngine — Specification 050 (ULTRA CRITICAL)

Discovers, validates, resolves and locks project dependencies.
Blocks incompatible, unsafe or unused packages. Builds lockfile + offline registry.
"""

from __future__ import annotations

import hashlib
import logging

from ....core.context import GenerationContext
from ....core.result import StageResult
from ...base.base_engine import BaseEngine
from .data_readers import (
    WorkspaceReader, FileSystemReader, ProjectContextReader,
    ArchitectureReader, UserRequestReader,
)
from .report_data import (
    DependencyManagementReport, ALL_SOURCES,
    SOURCE_WORKSPACE, SOURCE_FILE_SYSTEM, SOURCE_PROJECT_CONTEXT,
    SOURCE_ARCHITECTURE, SOURCE_USER_REQUEST,
)
from .resolver import DependencyResolver
from .cache_manager import CacheManager
from .quality_gate import QualityGate
from .blueprint_builder import BlueprintBuilder

_log = logging.getLogger("engine.dependency_management")


class DependencyManagementEngine(BaseEngine):
    """Specification 050 — Intelligent Dependency & Package Management Engine."""

    def __init__(self) -> None:
        super().__init__(
            name="dependency_management",
            version="1.0.0",
            description=(
                "Discovers, validates, resolves and locks dependencies. "
                "Detects conflicts, unused and vulnerable packages. "
                "Builds lockfile and offline verified registry."
            ),
            tags=["dependencies", "packages", "lockfile", "security", "versions"],
            metadata={"specification": "050", "priority": "ULTRA_CRITICAL"},
        )
        self._ws_reader = WorkspaceReader()
        self._fs_reader = FileSystemReader()
        self._ctx_reader = ProjectContextReader()
        self._arch_reader = ArchitectureReader()
        self._request_reader = UserRequestReader()
        self._resolver = DependencyResolver()
        self._cache = CacheManager(enabled=True)
        self._quality_gate = QualityGate()
        self._builder = BlueprintBuilder()

    def execute(self, context: GenerationContext) -> StageResult:
        try:
            _log.info("DependencyManagementEngine starting (Spec 050)")

            request_data = self._request_reader.read(context)
            ws_data = self._ws_reader.read(context)
            fs_data = self._fs_reader.read(context)
            ctx_data = self._ctx_reader.read(context)
            arch_data = self._arch_reader.read(context)

            sources_used = []
            sources_missing = []
            for key, data in (
                (SOURCE_USER_REQUEST, request_data),
                (SOURCE_WORKSPACE, ws_data),
                (SOURCE_FILE_SYSTEM, fs_data),
                (SOURCE_PROJECT_CONTEXT, ctx_data),
                (SOURCE_ARCHITECTURE, arch_data),
            ):
                if data.available:
                    sources_used.append(key)
                else:
                    sources_missing.append(key)

            cache_payload = str(sorted(sources_used)) + str(
                (request_data.raw or {}).get("requirements")
                or (request_data.raw or {}).get("language")
                or ""
            )
            cache_key = hashlib.sha256(cache_payload.encode("utf-8")).hexdigest()[:32]

            cached = self._cache.get(cache_key)
            if cached is not None:
                try:
                    report = DependencyManagementReport(**{
                        k: v for k, v in cached.items()
                        if k in DependencyManagementReport.__dataclass_fields__
                    })
                except Exception:
                    report = None
                if report is not None:
                    report.cache_info = self._cache.info_for_hit(cache_key)
                    context.set("dependency_management_report", report)
                    return self.ok(
                        outputs={"dependency_management_report": report.to_dict()},
                        metadata={"cache": "hit"},
                    )

            (
                dependencies, conflicts, security_issues, unused,
                lockfile, registry, health,
            ) = self._resolver.resolve(request_data, ctx_data, fs_data, arch_data)

            self_ok = self._resolver.self_verify(
                dependencies, conflicts, security_issues,
            )

            confidence = self._confidence(
                sources_used, sources_missing, dependencies, health, self_ok,
            )

            report = self._builder.build(
                dependencies=dependencies,
                conflicts=conflicts,
                security_issues=security_issues,
                unused=unused,
                lockfile=lockfile,
                registry=registry,
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
            context.set("dependency_management_report", report)

            _log.info(
                "DependencyManagementEngine finished — verdict=%s deps=%d "
                "conflicts=%d health=%.1f",
                verdict, len(dependencies), len(conflicts), health.overall,
            )

            if not passed:
                return self.failed(
                    errors=[
                        f"Dependency Management failed quality gate "
                        f"(verdict={verdict})"
                    ],
                    outputs={"dependency_management_report": report_dict},
                    warnings=[f.message for f in gate_findings],
                )
            return self.ok(
                outputs={"dependency_management_report": report_dict},
                metadata={
                    "report_id": report.report_id,
                    "verdict": verdict,
                    "dependency_count": len(dependencies),
                    "conflict_count": len(conflicts),
                    "unsafe_count": len(security_issues),
                    "unused_count": len(unused),
                    "health_overall": health.overall,
                    "self_verification_passed": self_ok,
                    "confidence": confidence,
                },
            )
        except Exception as exc:
            _log.exception("DependencyManagementEngine crashed: %s", exc)
            return self.failed(errors=[f"DependencyManagementEngine error: {exc}"])

    def _confidence(self, used, missing, dependencies, health, self_ok) -> float:
        total = len(ALL_SOURCES)
        ratio = len(used) / total if total else 0.0
        health_f = (health.overall / 100.0) if health else 0.0
        richness = min(1.0, len(dependencies) / 5.0)
        penalty = 0.0 if self_ok else 0.25
        conf = (0.25 * ratio) + (0.35 * health_f) + (0.20 * richness) + 0.20 - penalty
        return round(max(0.0, min(1.0, conf)), 3)


__all__ = ["DependencyManagementEngine"]
