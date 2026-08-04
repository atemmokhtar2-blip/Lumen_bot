"""BlueprintBuilder — Specification 056"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import List, Optional

from .report_data import (
    ResourceManagementReport, ResourceQuota, ResourceUsage, LeakRecord,
    CleanupAction, SystemSnapshot, CacheInfo, ResourceProvenance,
    CONFIDENCE_HIGH, CONFIDENCE_MEDIUM, CONFIDENCE_LOW,
    CONFIDENCE_HIGH_THRESHOLD, CONFIDENCE_MEDIUM_THRESHOLD, VERDICT_NOT_READY,
)

_log = logging.getLogger("engine.resource_management.blueprint_builder")


class BlueprintBuilder:
    def build(
        self,
        quotas: List[ResourceQuota],
        usage: List[ResourceUsage],
        leaks: List[LeakRecord],
        cleanups: List[CleanupAction],
        system: SystemSnapshot,
        sources_used: List[str],
        sources_missing: List[str],
        recovered: bool = False,
        self_verification_passed: bool = False,
        cache_info: Optional[CacheInfo] = None,
        confidence: float = 0.0,
    ) -> ResourceManagementReport:
        conf_level = (
            CONFIDENCE_HIGH if confidence >= CONFIDENCE_HIGH_THRESHOLD
            else CONFIDENCE_MEDIUM if confidence >= CONFIDENCE_MEDIUM_THRESHOLD
            else CONFIDENCE_LOW
        )
        over = sum(1 for u in usage if u.over_limit)
        report = ResourceManagementReport(
            report_id=str(uuid.uuid4()),
            quotas=quotas,
            usage=usage,
            leaks=leaks,
            cleanups=cleanups,
            system=system,
            findings=[],
            engine_count=len(quotas),
            over_limit_count=over,
            leak_count=len(leaks),
            recovered=recovered,
            self_verification_passed=self_verification_passed,
            readiness_status=VERDICT_NOT_READY,
            verdict=VERDICT_NOT_READY,
            cache_info=cache_info or CacheInfo(),
            provenance=ResourceProvenance(
                engine_name="resource_management",
                engine_version="1.0.0",
                sources_used=list(sources_used),
                sources_missing=list(sources_missing),
                generated_at=datetime.now(timezone.utc).isoformat(),
                confidence=confidence,
                confidence_level=conf_level,
                self_verification_passed=self_verification_passed,
            ),
            is_empty=len(quotas) == 0,
        )
        _log.info(
            "BlueprintBuilder produced %s (engines=%d over=%d leaks=%d)",
            report.report_id[:8], len(quotas), over, len(leaks),
        )
        return report


__all__ = ["BlueprintBuilder"]
