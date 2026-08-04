"""BlueprintBuilder — Specification 047"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import List, Optional

from .report_data import (
    GitOperationsReport, GitOperation, CommitInfo, BranchInfo, ConflictInfo,
    HistoryEntry, CacheInfo, GitProvenance,
    STATUS_DENIED, STATUS_FAILED, STATUS_AWAITING_CONFIRMATION,
    CONFIDENCE_HIGH, CONFIDENCE_MEDIUM, CONFIDENCE_LOW,
    CONFIDENCE_HIGH_THRESHOLD, CONFIDENCE_MEDIUM_THRESHOLD, VERDICT_NOT_READY,
)

_log = logging.getLogger("engine.git_operations.blueprint_builder")


class BlueprintBuilder:
    def build(
        self,
        operations: List[GitOperation],
        commits: List[CommitInfo],
        branches: List[BranchInfo],
        conflicts: List[ConflictInfo],
        history: List[HistoryEntry],
        sources_used: List[str],
        sources_missing: List[str],
        user_verified: bool = False,
        permission_ok: bool = False,
        repo_verified: bool = False,
        self_verification_passed: bool = False,
        cache_info: Optional[CacheInfo] = None,
        confidence: float = 0.0,
    ) -> GitOperationsReport:
        conf_level = (
            CONFIDENCE_HIGH if confidence >= CONFIDENCE_HIGH_THRESHOLD
            else CONFIDENCE_MEDIUM if confidence >= CONFIDENCE_MEDIUM_THRESHOLD
            else CONFIDENCE_LOW
        )
        denied = sum(1 for o in operations if o.status == STATUS_DENIED)
        failed = sum(1 for o in operations if o.status == STATUS_FAILED)
        awaiting = sum(1 for o in operations if o.status == STATUS_AWAITING_CONFIRMATION)
        report = GitOperationsReport(
            report_id=str(uuid.uuid4()),
            operations=operations,
            commits=commits,
            branches=branches,
            conflicts=conflicts,
            history=history,
            findings=[],
            operation_count=len(operations),
            denied_count=denied,
            failed_count=failed,
            awaiting_confirmation_count=awaiting,
            user_verified=user_verified,
            permission_ok=permission_ok,
            repo_verified=repo_verified,
            self_verification_passed=self_verification_passed,
            readiness_status=VERDICT_NOT_READY,
            verdict=VERDICT_NOT_READY,
            cache_info=cache_info or CacheInfo(),
            provenance=GitProvenance(
                engine_name="git_operations",
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
            "BlueprintBuilder produced %s (ops=%d denied=%d awaiting=%d)",
            report.report_id[:8], len(operations), denied, awaiting,
        )
        return report


__all__ = ["BlueprintBuilder"]
