"""BlueprintBuilder — Specification 061"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import List, Optional

from .report_data import (
    ServiceManagementReport, ServiceRecord, ServiceHealth, LifecycleEvent,
    RecoveryRecord, ResourceAllocation, LoadSample, CacheInfo, ServiceProvenance,
    CONFIDENCE_HIGH, CONFIDENCE_MEDIUM, CONFIDENCE_LOW,
    CONFIDENCE_HIGH_THRESHOLD, CONFIDENCE_MEDIUM_THRESHOLD, VERDICT_NOT_READY,
    STATE_STARTED, STATE_FAILED,
)

_log = logging.getLogger("engine.service_management.blueprint_builder")


class BlueprintBuilder:
    def build(
        self,
        services: List[ServiceRecord],
        health: List[ServiceHealth],
        lifecycle_events: List[LifecycleEvent],
        recoveries: List[RecoveryRecord],
        allocations: List[ResourceAllocation],
        loads: List[LoadSample],
        sources_used: List[str],
        sources_missing: List[str],
        unregistered_attempts: int = 0,
        dependency_violations: int = 0,
        self_verification_passed: bool = False,
        cache_info: Optional[CacheInfo] = None,
        confidence: float = 0.0,
    ) -> ServiceManagementReport:
        conf_level = (
            CONFIDENCE_HIGH if confidence >= CONFIDENCE_HIGH_THRESHOLD
            else CONFIDENCE_MEDIUM if confidence >= CONFIDENCE_MEDIUM_THRESHOLD
            else CONFIDENCE_LOW
        )
        started = sum(1 for s in services if s.state == STATE_STARTED)
        failed = sum(1 for s in services if s.state == STATE_FAILED)
        report = ServiceManagementReport(
            report_id=str(uuid.uuid4()),
            services=services,
            health=health,
            lifecycle_events=lifecycle_events,
            recoveries=recoveries,
            allocations=allocations,
            loads=loads,
            findings=[],
            service_count=len(services),
            started_count=started,
            failed_count=failed,
            recovery_count=len(recoveries),
            unregistered_attempts=unregistered_attempts,
            dependency_violations=dependency_violations,
            self_verification_passed=self_verification_passed,
            readiness_status=VERDICT_NOT_READY,
            verdict=VERDICT_NOT_READY,
            cache_info=cache_info or CacheInfo(),
            provenance=ServiceProvenance(
                engine_name="service_management",
                engine_version="1.0.0",
                sources_used=list(sources_used),
                sources_missing=list(sources_missing),
                generated_at=datetime.now(timezone.utc).isoformat(),
                confidence=confidence,
                confidence_level=conf_level,
                self_verification_passed=self_verification_passed,
            ),
            is_empty=len(services) == 0,
        )
        _log.info(
            "BlueprintBuilder produced %s (services=%d started=%d failed=%d)",
            report.report_id[:8], len(services), started, failed,
        )
        return report


__all__ = ["BlueprintBuilder"]
