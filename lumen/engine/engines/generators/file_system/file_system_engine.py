"""
FileSystemEngine — Specification 048 (CRITICAL)

Abstract file-system layer for the platform. All engines must go through this
layer. Pipeline: path validation → permission → backup → execute → integrity.
Workspace isolation; automatic recovery from backup on failure.
"""

from __future__ import annotations

import hashlib
import logging

from ....core.context import GenerationContext
from ....core.result import StageResult
from ...base.base_engine import BaseEngine
from .data_readers import (
    GitOperationsReader, RepositoryManagementReader,
    ProjectContextReader, UserRequestReader,
)
from .report_data import (
    FileSystemReport, ALL_SOURCES,
    SOURCE_GIT_OPERATIONS, SOURCE_REPOSITORY_MANAGEMENT,
    SOURCE_PROJECT_CONTEXT, SOURCE_USER_REQUEST,
)
from .fs_manager import FileSystemManager
from .cache_manager import CacheManager
from .quality_gate import QualityGate
from .blueprint_builder import BlueprintBuilder

_log = logging.getLogger("engine.file_system")


class FileSystemEngine(BaseEngine):
    """Specification 048 — Intelligent File System Engine."""


    declared_engine_id = "file_system"
    declared_priority = 120
    declared_dependencies = ['dependency_resolver']
    declared_role = "generation"

    def __init__(self) -> None:
        super().__init__(
            name="file_system",
            engine_id="file_system",
            priority=120,
            dependencies=['dependency_resolver'],
            role="generation",
            version="1.0.0",
            description=(
                "Abstract FS layer: create/read/write/delete/move files and folders "
                "with path validation, permissions, automatic backup, integrity checks "
                "and workspace isolation. No data loss."
            ),
            tags=["filesystem", "backup", "integrity", "workspace", "safe-ops"],
            metadata={"specification": "048", "priority": "CRITICAL"},
        )
        self._git_reader = GitOperationsReader()
        self._repo_reader = RepositoryManagementReader()
        self._ctx_reader = ProjectContextReader()
        self._request_reader = UserRequestReader()
        self._manager = FileSystemManager()
        self._cache = CacheManager(enabled=True)
        self._quality_gate = QualityGate()
        self._builder = BlueprintBuilder()

    def execute(self, context: GenerationContext) -> StageResult:
        try:
            _log.info("FileSystemEngine starting (Spec 048)")

            request_data = self._request_reader.read(context)
            git_data = self._git_reader.read(context)
            repo_data = self._repo_reader.read(context)
            ctx_data = self._ctx_reader.read(context)

            sources_used = []
            sources_missing = []
            for key, data in (
                (SOURCE_USER_REQUEST, request_data),
                (SOURCE_GIT_OPERATIONS, git_data),
                (SOURCE_REPOSITORY_MANAGEMENT, repo_data),
                (SOURCE_PROJECT_CONTEXT, ctx_data),
            ):
                if data.available:
                    sources_used.append(key)
                else:
                    sources_missing.append(key)

            cache_payload = str(sorted(sources_used)) + str(
                (request_data.raw or {}).get("operation")
                or (request_data.raw or {}).get("path")
                or ""
            )
            cache_key = hashlib.sha256(cache_payload.encode("utf-8")).hexdigest()[:32]

            cached = self._cache.get(cache_key)
            if cached is not None:
                try:
                    report = FileSystemReport(**{
                        k: v for k, v in cached.items()
                        if k in FileSystemReport.__dataclass_fields__
                    })
                except Exception:
                    report = None
                if report is not None:
                    report.cache_info = self._cache.info_for_hit(cache_key)
                    context.set("file_system_report", report)
                    return self.ok(
                        outputs={"file_system_report": report.to_dict()},
                        metadata={"cache": "hit"},
                    )

            (
                operations, path_checks, perm_checks, backups,
                integrity, duplicates, isolated,
            ) = self._manager.process(request_data, ctx_data, git_data, repo_data)

            self_ok = self._manager.self_verify(
                operations, path_checks, backups, integrity, isolated,
            )

            confidence = self._confidence(
                sources_used, sources_missing, operations, isolated,
            )

            report = self._builder.build(
                operations=operations,
                path_checks=path_checks,
                permission_checks=perm_checks,
                backups=backups,
                integrity=integrity,
                duplicates=duplicates,
                sources_used=sources_used,
                sources_missing=sources_missing,
                workspace_isolated=isolated,
                self_verification_passed=self_ok,
                confidence=confidence,
            )

            gate_findings, passed, verdict = self._quality_gate.validate(report)
            report.findings.extend(gate_findings)
            report.verdict = verdict
            report.readiness_status = verdict
            report.self_verification_passed = self_ok
            report.workspace_isolated = isolated

            report_dict = report.to_dict()
            report.cache_info = self._cache.put(cache_key, report_dict)
            context.set("file_system_report", report)

            _log.info(
                "FileSystemEngine finished — verdict=%s ops=%d denied=%d "
                "recovered=%d isolated=%s",
                verdict, len(operations), report.denied_count,
                report.recovered_count, isolated,
            )

            if not passed:
                return self.failed(
                    errors=[
                        f"File System failed quality gate (verdict={verdict})"
                    ],
                    outputs={"file_system_report": report_dict},
                    warnings=[f.message for f in gate_findings],
                )
            return self.ok(
                outputs={"file_system_report": report_dict},
                metadata={
                    "report_id": report.report_id,
                    "verdict": verdict,
                    "operation_count": len(operations),
                    "denied_count": report.denied_count,
                    "failed_count": report.failed_count,
                    "recovered_count": report.recovered_count,
                    "workspace_isolated": isolated,
                    "self_verification_passed": self_ok,
                    "confidence": confidence,
                },
            )
        except Exception as exc:
            _log.exception("FileSystemEngine crashed: %s", exc)
            return self.failed(errors=[f"FileSystemEngine error: {exc}"])

    def _confidence(self, used, missing, operations, isolated) -> float:
        total = len(ALL_SOURCES)
        ratio = len(used) / total if total else 0.0
        failed = sum(
            1 for o in operations
            if getattr(o, "status", "") == "failed" and not getattr(o, "recovered", False)
        )
        penalty = min(0.4, failed * 0.1 + (0.0 if isolated else 0.25))
        conf = (0.35 * ratio) + (0.35 if isolated else 0.0) + 0.30 - penalty
        return round(max(0.0, min(1.0, conf)), 3)


__all__ = ["FileSystemEngine"]
