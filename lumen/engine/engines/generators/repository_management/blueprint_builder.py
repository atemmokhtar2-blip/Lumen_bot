"""BlueprintBuilder — Specification 046"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import List, Optional

from .report_data import (
    RepositoryManagementReport, PermissionCheck, OperationPlan,
    OperationResult, RepoDiscovery, CacheInfo, RepoProvenance,
    STATUS_DENIED, STATUS_FAILED,
    CONFIDENCE_HIGH, CONFIDENCE_MEDIUM, CONFIDENCE_LOW,
    CONFIDENCE_HIGH_THRESHOLD, CONFIDENCE_MEDIUM_THRESHOLD, VERDICT_NOT_READY,
)

_log = logging.getLogger("engine.repository_management.blueprint_builder")


class BlueprintBuilder:
    def build(
        self,
        permission_checks: List[PermissionCheck],
        plans: List[OperationPlan],
        results: List[OperationResult],
        discoveries: List[RepoDiscovery],
        sources_used: List[str],
        sources_missing: List[str],
        ownership_verified: bool = False,
        self_verification_passed: bool = False,
        cache_info: Optional[CacheInfo] = None,
        confidence: float = 0.0,
    ) -> RepositoryManagementReport:
        conf_level = (
            CONFIDENCE_HIGH if confidence >= CONFIDENCE_HIGH_THRESHOLD
            else CONFIDENCE_MEDIUM if confidence >= CONFIDENCE_MEDIUM_THRESHOLD
            else CONFIDENCE_LOW
        )
        denied = sum(1 for r in results if r.status == STATUS_DENIED)
        failed = sum(1 for r in results if r.status == STATUS_FAILED)
        report = RepositoryManagementReport(
            report_id=str(uuid.uuid4()),
            permission_checks=permission_checks,
            plans=plans,
            results=results,
            discoveries=discoveries,
            findings=[],
            operation_count=len(results),
            denied_count=denied,
            failed_count=failed,
            ownership_verified=ownership_verified,
            self_verification_passed=self_verification_passed,
            readiness_status=VERDICT_NOT_READY,
            verdict=VERDICT_NOT_READY,
            cache_info=cache_info or CacheInfo(),
            provenance=RepoProvenance(
                engine_name="repository_management",
                engine_version="1.0.0",
                sources_used=list(sources_used),
                sources_missing=list(sources_missing),
                generated_at=datetime.now(timezone.utc).isoformat(),
                confidence=confidence,
                confidence_level=conf_level,
                self_verification_passed=self_verification_passed,
            ),
            is_empty=len(results) == 0 and len(plans) == 0,
        )
        _log.info(
            "BlueprintBuilder produced %s (ops=%d denied=%d failed=%d)",
            report.report_id[:8], len(results), denied, failed,
        )
        return report


__all__ = ["BlueprintBuilder"]
