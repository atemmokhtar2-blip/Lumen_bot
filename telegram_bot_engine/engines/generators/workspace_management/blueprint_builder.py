"""BlueprintBuilder — Specification 049"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import List, Optional

from .report_data import (
    WorkspaceManagementReport, WorkspaceRecord, WorkspaceAction,
    ResourceUsage, SnapshotRecord, ValidationResult, CacheInfo, WorkspaceProvenance,
    STATUS_FAILED,
    CONFIDENCE_HIGH, CONFIDENCE_MEDIUM, CONFIDENCE_LOW,
    CONFIDENCE_HIGH_THRESHOLD, CONFIDENCE_MEDIUM_THRESHOLD, VERDICT_NOT_READY,
)

_log = logging.getLogger("engine.workspace_management.blueprint_builder")


class BlueprintBuilder:
    def build(
        self,
        workspaces: List[WorkspaceRecord],
        actions: List[WorkspaceAction],
        resources: List[ResourceUsage],
        snapshots: List[SnapshotRecord],
        validations: List[ValidationResult],
        sources_used: List[str],
        sources_missing: List[str],
        isolation_ok: bool = True,
        self_verification_passed: bool = False,
        cache_info: Optional[CacheInfo] = None,
        confidence: float = 0.0,
    ) -> WorkspaceManagementReport:
        conf_level = (
            CONFIDENCE_HIGH if confidence >= CONFIDENCE_HIGH_THRESHOLD
            else CONFIDENCE_MEDIUM if confidence >= CONFIDENCE_MEDIUM_THRESHOLD
            else CONFIDENCE_LOW
        )
        failed = sum(1 for a in actions if a.status == STATUS_FAILED)
        report = WorkspaceManagementReport(
            report_id=str(uuid.uuid4()),
            workspaces=workspaces,
            actions=actions,
            resources=resources,
            snapshots=snapshots,
            validations=validations,
            findings=[],
            workspace_count=len(workspaces),
            action_count=len(actions),
            failed_count=failed,
            isolation_ok=isolation_ok,
            self_verification_passed=self_verification_passed,
            readiness_status=VERDICT_NOT_READY,
            verdict=VERDICT_NOT_READY,
            cache_info=cache_info or CacheInfo(),
            provenance=WorkspaceProvenance(
                engine_name="workspace_management",
                engine_version="1.0.0",
                sources_used=list(sources_used),
                sources_missing=list(sources_missing),
                generated_at=datetime.now(timezone.utc).isoformat(),
                confidence=confidence,
                confidence_level=conf_level,
                self_verification_passed=self_verification_passed,
            ),
            is_empty=len(workspaces) == 0 and len(actions) == 0,
        )
        _log.info(
            "BlueprintBuilder produced %s (ws=%d actions=%d isolation=%s)",
            report.report_id[:8], len(workspaces), len(actions), isolation_ok,
        )
        return report


__all__ = ["BlueprintBuilder"]
