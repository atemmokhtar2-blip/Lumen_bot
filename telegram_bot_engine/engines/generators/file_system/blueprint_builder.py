"""BlueprintBuilder — Specification 048"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import List, Optional

from .report_data import (
    FileSystemReport, FileOperation, PathCheck, PermissionCheck,
    BackupRecord, IntegrityResult, DuplicateInfo, CacheInfo, FSProvenance,
    STATUS_DENIED, STATUS_FAILED, STATUS_RECOVERED,
    CONFIDENCE_HIGH, CONFIDENCE_MEDIUM, CONFIDENCE_LOW,
    CONFIDENCE_HIGH_THRESHOLD, CONFIDENCE_MEDIUM_THRESHOLD, VERDICT_NOT_READY,
)

_log = logging.getLogger("engine.file_system.blueprint_builder")


class BlueprintBuilder:
    def build(
        self,
        operations: List[FileOperation],
        path_checks: List[PathCheck],
        permission_checks: List[PermissionCheck],
        backups: List[BackupRecord],
        integrity: List[IntegrityResult],
        duplicates: List[DuplicateInfo],
        sources_used: List[str],
        sources_missing: List[str],
        workspace_isolated: bool = True,
        self_verification_passed: bool = False,
        cache_info: Optional[CacheInfo] = None,
        confidence: float = 0.0,
    ) -> FileSystemReport:
        conf_level = (
            CONFIDENCE_HIGH if confidence >= CONFIDENCE_HIGH_THRESHOLD
            else CONFIDENCE_MEDIUM if confidence >= CONFIDENCE_MEDIUM_THRESHOLD
            else CONFIDENCE_LOW
        )
        denied = sum(1 for o in operations if o.status == STATUS_DENIED)
        failed = sum(1 for o in operations if o.status == STATUS_FAILED)
        recovered = sum(1 for o in operations if o.status == STATUS_RECOVERED or o.recovered)
        report = FileSystemReport(
            report_id=str(uuid.uuid4()),
            operations=operations,
            path_checks=path_checks,
            permission_checks=permission_checks,
            backups=backups,
            integrity=integrity,
            duplicates=duplicates,
            findings=[],
            operation_count=len(operations),
            denied_count=denied,
            failed_count=failed,
            recovered_count=recovered,
            workspace_isolated=workspace_isolated,
            self_verification_passed=self_verification_passed,
            readiness_status=VERDICT_NOT_READY,
            verdict=VERDICT_NOT_READY,
            cache_info=cache_info or CacheInfo(),
            provenance=FSProvenance(
                engine_name="file_system",
                engine_version="1.0.0",
                sources_used=list(sources_used),
                sources_missing=list(sources_missing),
                generated_at=datetime.now(timezone.utc).isoformat(),
                confidence=confidence,
                confidence_level=conf_level,
                self_verification_passed=self_verification_passed,
            ),
            is_empty=len(operations) == 0,
        )
        _log.info(
            "BlueprintBuilder produced %s (ops=%d denied=%d recovered=%d)",
            report.report_id[:8], len(operations), denied, recovered,
        )
        return report


__all__ = ["BlueprintBuilder"]
