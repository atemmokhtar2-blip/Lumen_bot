"""
RepositoryManagementEngine — Specification 046 (CRITICAL)

Manages user repositories only after ownership and permission checks.
Never acts autonomously — executes only explicit user requests.
"""

from __future__ import annotations

import hashlib
import logging

from ....core.context import GenerationContext
from ....core.result import StageResult
from ...base.base_engine import BaseEngine
from .data_readers import (
    ProjectContextReader, ProductionReadinessReader, UserRequestReader,
)
from .report_data import (
    RepositoryManagementReport, ALL_SOURCES,
    SOURCE_PROJECT_CONTEXT, SOURCE_PRODUCTION_READINESS, SOURCE_USER_REQUEST,
)
from .manager import RepositoryManager
from .cache_manager import CacheManager
from .quality_gate import QualityGate
from .blueprint_builder import BlueprintBuilder

_log = logging.getLogger("engine.repository_management")


class RepositoryManagementEngine(BaseEngine):
    """Specification 046 — Intelligent Repository Management Engine."""


    declared_engine_id = "repository_management"
    declared_priority = 190
    declared_dependencies = ['git_operations']
    declared_role = "infra"

    def __init__(self) -> None:
        super().__init__(
            name="repository_management",
            engine_id="repository_management",
            priority=190,
            dependencies=['git_operations'],
            role="infra",
            version="1.0.0",
            description=(
                "Manages user repositories (clone/pull/push/branch/create) only "
                "after ownership and permission verification. Never autonomous."
            ),
            tags=["repository", "git", "permissions", "ownership", "safe-ops"],
            metadata={"specification": "046", "priority": "CRITICAL"},
        )
        self._ctx_reader = ProjectContextReader()
        self._readiness_reader = ProductionReadinessReader()
        self._request_reader = UserRequestReader()
        self._manager = RepositoryManager()
        self._cache = CacheManager(enabled=True)
        self._quality_gate = QualityGate()
        self._builder = BlueprintBuilder()

    def execute(self, context: GenerationContext) -> StageResult:
        try:
            _log.info("RepositoryManagementEngine starting (Spec 046)")

            request_data = self._request_reader.read(context)
            ctx_data = self._ctx_reader.read(context)
            readiness_data = self._readiness_reader.read(context)

            sources_used = []
            sources_missing = []
            for key, data in (
                (SOURCE_USER_REQUEST, request_data),
                (SOURCE_PROJECT_CONTEXT, ctx_data),
                (SOURCE_PRODUCTION_READINESS, readiness_data),
            ):
                if data.available:
                    sources_used.append(key)
                else:
                    sources_missing.append(key)

            cache_payload = str(sorted(sources_used)) + str(
                (request_data.raw or {}).get("operation")
                or (request_data.raw or {}).get("repository_url")
                or ""
            )
            cache_key = hashlib.sha256(cache_payload.encode("utf-8")).hexdigest()[:32]

            cached = self._cache.get(cache_key)
            if cached is not None:
                try:
                    report = RepositoryManagementReport(**{
                        k: v for k, v in cached.items()
                        if k in RepositoryManagementReport.__dataclass_fields__
                    })
                except Exception:
                    report = None
                if report is not None:
                    report.cache_info = self._cache.info_for_hit(cache_key)
                    context.set("repository_management_report", report)
                    return self.ok(
                        outputs={"repository_management_report": report.to_dict()},
                        metadata={"cache": "hit"},
                    )

            checks, plans, results, discoveries, owner_ok = self._manager.process(
                request_data, ctx_data, readiness_data,
            )

            self_ok = self._manager.self_verify(checks, results, owner_ok)

            confidence = self._confidence(
                sources_used, sources_missing, results, owner_ok,
            )

            report = self._builder.build(
                permission_checks=checks,
                plans=plans,
                results=results,
                discoveries=discoveries,
                sources_used=sources_used,
                sources_missing=sources_missing,
                ownership_verified=owner_ok,
                self_verification_passed=self_ok,
                confidence=confidence,
            )

            gate_findings, passed, verdict = self._quality_gate.validate(report)
            report.findings.extend(gate_findings)
            report.verdict = verdict
            report.readiness_status = verdict
            report.self_verification_passed = self_ok
            report.ownership_verified = owner_ok

            report_dict = report.to_dict()
            report.cache_info = self._cache.put(cache_key, report_dict)
            context.set("repository_management_report", report)

            _log.info(
                "RepositoryManagementEngine finished — verdict=%s ops=%d "
                "denied=%d owner_ok=%s",
                verdict, len(results), report.denied_count, owner_ok,
            )

            if not passed:
                return self.failed(
                    errors=[
                        f"Repository Management failed quality gate "
                        f"(verdict={verdict})"
                    ],
                    outputs={"repository_management_report": report_dict},
                    warnings=[f.message for f in gate_findings],
                )
            return self.ok(
                outputs={"repository_management_report": report_dict},
                metadata={
                    "report_id": report.report_id,
                    "verdict": verdict,
                    "operation_count": len(results),
                    "denied_count": report.denied_count,
                    "failed_count": report.failed_count,
                    "ownership_verified": owner_ok,
                    "self_verification_passed": self_ok,
                    "confidence": confidence,
                },
            )
        except Exception as exc:
            _log.exception("RepositoryManagementEngine crashed: %s", exc)
            return self.failed(errors=[f"RepositoryManagementEngine error: {exc}"])

    def _confidence(self, used, missing, results, owner_ok) -> float:
        total = len(ALL_SOURCES)
        ratio = len(used) / total if total else 0.0
        denied = sum(1 for r in results if getattr(r, "status", "") == "denied")
        failed = sum(1 for r in results if getattr(r, "status", "") == "failed")
        penalty = min(0.4, failed * 0.1 + (0.0 if owner_ok else 0.2))
        conf = (0.40 * ratio) + (0.30 if owner_ok else 0.0) + 0.30 - penalty
        if results and denied == len(results):
            conf = max(conf, 0.7)  # secure denial is confident
        return round(max(0.0, min(1.0, conf)), 3)


__all__ = ["RepositoryManagementEngine"]
