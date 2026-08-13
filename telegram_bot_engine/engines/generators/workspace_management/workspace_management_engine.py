"""
WorkspaceManagementEngine — Specification 049 (CRITICAL)

Manages fully isolated project workspaces with lifecycle, resources,
monitoring, snapshots, recovery and cleanup. No cross-project access.
"""

from __future__ import annotations

import hashlib
import logging

from ....core.context import GenerationContext
from ....core.result import StageResult
from ...base.base_engine import BaseEngine
from .data_readers import (
    FileSystemReader, GitOperationsReader, RepositoryManagementReader,
    ProjectContextReader, UserRequestReader,
)
from .report_data import (
    WorkspaceManagementReport, ALL_SOURCES,
    SOURCE_FILE_SYSTEM, SOURCE_GIT_OPERATIONS, SOURCE_REPOSITORY_MANAGEMENT,
    SOURCE_PROJECT_CONTEXT, SOURCE_USER_REQUEST,
)
from .manager import WorkspaceManager
from .cache_manager import CacheManager
from .quality_gate import QualityGate
from .blueprint_builder import BlueprintBuilder

_log = logging.getLogger("engine.workspace_management")


class WorkspaceManagementEngine(BaseEngine):
    """Specification 049 — Intelligent Workspace Management Engine."""

    def __init__(self) -> None:
        super().__init__(
            name="workspace_management",
            version="1.0.0",
            description=(
                "Manages isolated project workspaces: create/open/suspend/resume/"
                "archive/delete, resources, monitoring, snapshots, recovery and cleanup."
            ),
            tags=["workspace", "isolation", "lifecycle", "snapshot", "resources"],
            metadata={"specification": "049", "priority": "CRITICAL"},
        )
        self._fs_reader = FileSystemReader()
        self._git_reader = GitOperationsReader()
        self._repo_reader = RepositoryManagementReader()
        self._ctx_reader = ProjectContextReader()
        self._request_reader = UserRequestReader()
        self._manager = WorkspaceManager()
        self._cache = CacheManager(enabled=True)
        self._quality_gate = QualityGate()
        self._builder = BlueprintBuilder()

    def execute(self, context: GenerationContext) -> StageResult:
        try:
            _log.info("WorkspaceManagementEngine starting (Spec 049)")

            request_data = self._request_reader.read(context)
            fs_data = self._fs_reader.read(context)
            git_data = self._git_reader.read(context)
            repo_data = self._repo_reader.read(context)
            ctx_data = self._ctx_reader.read(context)

            sources_used = []
            sources_missing = []
            for key, data in (
                (SOURCE_USER_REQUEST, request_data),
                (SOURCE_FILE_SYSTEM, fs_data),
                (SOURCE_GIT_OPERATIONS, git_data),
                (SOURCE_REPOSITORY_MANAGEMENT, repo_data),
                (SOURCE_PROJECT_CONTEXT, ctx_data),
            ):
                if data.available:
                    sources_used.append(key)
                else:
                    sources_missing.append(key)

            cache_payload = str(sorted(sources_used)) + str(
                (request_data.raw or {}).get("workspace_id")
                or (request_data.raw or {}).get("action")
                or ""
            )
            cache_key = hashlib.sha256(cache_payload.encode("utf-8")).hexdigest()[:32]

            cached = self._cache.get(cache_key)
            if cached is not None:
                try:
                    report = WorkspaceManagementReport(**{
                        k: v for k, v in cached.items()
                        if k in WorkspaceManagementReport.__dataclass_fields__
                    })
                except Exception:
                    report = None
                if report is not None:
                    report.cache_info = self._cache.info_for_hit(cache_key)
                    context.set("workspace_management_report", report)
                    return self.ok(
                        outputs={"workspace_management_report": report.to_dict()},
                        metadata={"cache": "hit"},
                    )

            (
                workspaces, actions, resources, snapshots, validations, isolation_ok,
            ) = self._manager.process(request_data, ctx_data, fs_data)

            self_ok = self._manager.self_verify(workspaces, actions, isolation_ok)

            confidence = self._confidence(
                sources_used, sources_missing, workspaces, isolation_ok,
            )

            report = self._builder.build(
                workspaces=workspaces,
                actions=actions,
                resources=resources,
                snapshots=snapshots,
                validations=validations,
                sources_used=sources_used,
                sources_missing=sources_missing,
                isolation_ok=isolation_ok,
                self_verification_passed=self_ok,
                confidence=confidence,
            )

            gate_findings, passed, verdict = self._quality_gate.validate(report)
            report.findings.extend(gate_findings)
            report.verdict = verdict
            report.readiness_status = verdict
            report.self_verification_passed = self_ok
            report.isolation_ok = isolation_ok

            report_dict = report.to_dict()
            report.cache_info = self._cache.put(cache_key, report_dict)
            context.set("workspace_management_report", report)

            _log.info(
                "WorkspaceManagementEngine finished — verdict=%s ws=%d "
                "actions=%d isolation=%s",
                verdict, len(workspaces), len(actions), isolation_ok,
            )

            if not passed:
                return self.failed(
                    errors=[
                        f"Workspace Management failed quality gate "
                        f"(verdict={verdict})"
                    ],
                    outputs={"workspace_management_report": report_dict},
                    warnings=[f.message for f in gate_findings],
                )
            return self.ok(
                outputs={"workspace_management_report": report_dict},
                metadata={
                    "report_id": report.report_id,
                    "verdict": verdict,
                    "workspace_count": len(workspaces),
                    "action_count": len(actions),
                    "failed_count": report.failed_count,
                    "isolation_ok": isolation_ok,
                    "self_verification_passed": self_ok,
                    "confidence": confidence,
                },
            )
        except Exception as exc:
            _log.exception("WorkspaceManagementEngine crashed: %s", exc)
            return self.failed(errors=[f"WorkspaceManagementEngine error: {exc}"])

    def _confidence(self, used, missing, workspaces, isolation_ok) -> float:
        total = len(ALL_SOURCES)
        ratio = len(used) / total if total else 0.0
        richness = min(1.0, len(workspaces) / 2.0)
        penalty = 0.0 if isolation_ok else 0.3
        conf = (0.35 * ratio) + (0.25 * richness) + (0.40 if isolation_ok else 0.1) - penalty
        return round(max(0.0, min(1.0, conf)), 3)


__all__ = ["WorkspaceManagementEngine"]
