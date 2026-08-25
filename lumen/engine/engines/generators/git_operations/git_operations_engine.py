"""
GitOperationsEngine — Specification 047 (CRITICAL)

Executes Git operations only after user, permission and repository checks.
Dangerous operations require explicit confirmation. No autonomous history rewrite.
"""

from __future__ import annotations

import hashlib
import logging

from ....core.context import GenerationContext
from ....core.result import StageResult
from ...base.base_engine import BaseEngine
from .data_readers import (
    RepositoryManagementReader, ProjectContextReader,
    ProductionReadinessReader, UserRequestReader,
)
from .report_data import (
    GitOperationsReport, ALL_SOURCES,
    SOURCE_REPOSITORY_MANAGEMENT, SOURCE_PROJECT_CONTEXT,
    SOURCE_USER_REQUEST, SOURCE_PRODUCTION_READINESS,
)
from .executor import GitExecutor
from .cache_manager import CacheManager
from .quality_gate import QualityGate
from .blueprint_builder import BlueprintBuilder

_log = logging.getLogger("engine.git_operations")


class GitOperationsEngine(BaseEngine):
    """Specification 047 — Intelligent Git Operations Engine."""


    declared_engine_id = "git_operations"
    declared_priority = 180
    declared_dependencies = ['component_detector']
    declared_role = "infra"

    def __init__(self) -> None:
        super().__init__(
            name="git_operations",
            engine_id="git_operations",
            priority=180,
            dependencies=['component_detector'],
            role="infra",
            version="1.0.0",
            description=(
                "Executes Git operations (clone/commit/push/branch/merge/…) after "
                "user, permission and repo verification. Dangerous ops need explicit "
                "confirmation; conflicts suggested only."
            ),
            tags=["git", "commit", "branch", "merge", "safe-mode", "history"],
            metadata={"specification": "047", "priority": "CRITICAL"},
        )
        self._repo_reader = RepositoryManagementReader()
        self._ctx_reader = ProjectContextReader()
        self._readiness_reader = ProductionReadinessReader()
        self._request_reader = UserRequestReader()
        self._executor = GitExecutor()
        self._cache = CacheManager(enabled=True)
        self._quality_gate = QualityGate()
        self._builder = BlueprintBuilder()

    def execute(self, context: GenerationContext) -> StageResult:
        try:
            _log.info("GitOperationsEngine starting (Spec 047)")

            request_data = self._request_reader.read(context)
            repo_data = self._repo_reader.read(context)
            ctx_data = self._ctx_reader.read(context)
            readiness_data = self._readiness_reader.read(context)

            sources_used = []
            sources_missing = []
            for key, data in (
                (SOURCE_USER_REQUEST, request_data),
                (SOURCE_REPOSITORY_MANAGEMENT, repo_data),
                (SOURCE_PROJECT_CONTEXT, ctx_data),
                (SOURCE_PRODUCTION_READINESS, readiness_data),
            ):
                if data.available:
                    sources_used.append(key)
                else:
                    sources_missing.append(key)

            cache_payload = str(sorted(sources_used)) + str(
                (request_data.raw or {}).get("operation")
                or (request_data.raw or {}).get("git_operation")
                or ""
            )
            cache_key = hashlib.sha256(cache_payload.encode("utf-8")).hexdigest()[:32]

            cached = self._cache.get(cache_key)
            if cached is not None:
                try:
                    report = GitOperationsReport(**{
                        k: v for k, v in cached.items()
                        if k in GitOperationsReport.__dataclass_fields__
                    })
                except Exception:
                    report = None
                if report is not None:
                    report.cache_info = self._cache.info_for_hit(cache_key)
                    context.set("git_operations_report", report)
                    return self.ok(
                        outputs={"git_operations_report": report.to_dict()},
                        metadata={"cache": "hit"},
                    )

            (
                operations, commits, branches, conflicts, history,
                user_ok, perm_ok, repo_ok,
            ) = self._executor.run(request_data, repo_data, ctx_data)

            self_ok = self._executor.self_verify(
                operations, user_ok, perm_ok, repo_ok,
            )

            confidence = self._confidence(
                sources_used, sources_missing, operations, user_ok, perm_ok, repo_ok,
            )

            report = self._builder.build(
                operations=operations,
                commits=commits,
                branches=branches,
                conflicts=conflicts,
                history=history,
                sources_used=sources_used,
                sources_missing=sources_missing,
                user_verified=user_ok,
                permission_ok=perm_ok,
                repo_verified=repo_ok,
                self_verification_passed=self_ok,
                confidence=confidence,
            )

            gate_findings, passed, verdict = self._quality_gate.validate(report)
            report.findings.extend(gate_findings)
            report.verdict = verdict
            report.readiness_status = verdict
            report.self_verification_passed = self_ok
            report.user_verified = user_ok
            report.permission_ok = perm_ok
            report.repo_verified = repo_ok

            report_dict = report.to_dict()
            report.cache_info = self._cache.put(cache_key, report_dict)
            context.set("git_operations_report", report)

            _log.info(
                "GitOperationsEngine finished — verdict=%s ops=%d denied=%d "
                "awaiting=%d",
                verdict, len(operations), report.denied_count,
                report.awaiting_confirmation_count,
            )

            if not passed:
                return self.failed(
                    errors=[
                        f"Git Operations failed quality gate (verdict={verdict})"
                    ],
                    outputs={"git_operations_report": report_dict},
                    warnings=[f.message for f in gate_findings],
                )
            return self.ok(
                outputs={"git_operations_report": report_dict},
                metadata={
                    "report_id": report.report_id,
                    "verdict": verdict,
                    "operation_count": len(operations),
                    "denied_count": report.denied_count,
                    "failed_count": report.failed_count,
                    "awaiting_confirmation_count": report.awaiting_confirmation_count,
                    "user_verified": user_ok,
                    "permission_ok": perm_ok,
                    "repo_verified": repo_ok,
                    "self_verification_passed": self_ok,
                    "confidence": confidence,
                },
            )
        except Exception as exc:
            _log.exception("GitOperationsEngine crashed: %s", exc)
            return self.failed(errors=[f"GitOperationsEngine error: {exc}"])

    def _confidence(
        self, used, missing, operations, user_ok, perm_ok, repo_ok
    ) -> float:
        total = len(ALL_SOURCES)
        ratio = len(used) / total if total else 0.0
        gates = sum([user_ok, perm_ok, repo_ok]) / 3.0
        failed = sum(1 for o in operations if getattr(o, "status", "") == "failed")
        penalty = min(0.4, failed * 0.1)
        conf = (0.30 * ratio) + (0.40 * gates) + 0.30 - penalty
        return round(max(0.0, min(1.0, conf)), 3)


__all__ = ["GitOperationsEngine"]
