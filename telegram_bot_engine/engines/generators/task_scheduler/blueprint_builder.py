"""BlueprintBuilder — Specification 063"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import List, Optional

from .report_data import (
    TaskSchedulerReport, ScheduledTask, ScheduleEvent, RetrySchedule,
    SchedulerStats, CacheInfo, SchedulerProvenance,
    CONFIDENCE_HIGH, CONFIDENCE_MEDIUM, CONFIDENCE_LOW,
    CONFIDENCE_HIGH_THRESHOLD, CONFIDENCE_MEDIUM_THRESHOLD, VERDICT_NOT_READY,
    STATE_COMPLETED, STATE_FAILED, STATE_CANCELLED, POLICY_PRIORITY,
)

_log = logging.getLogger("engine.task_scheduler.blueprint_builder")


class BlueprintBuilder:
    def build(
        self,
        tasks: List[ScheduledTask],
        events: List[ScheduleEvent],
        retries: List[RetrySchedule],
        stats: SchedulerStats,
        sources_used: List[str],
        sources_missing: List[str],
        policy: str = POLICY_PRIORITY,
        dependency_violations: int = 0,
        early_start_violations: int = 0,
        load_throttled: int = 0,
        self_verification_passed: bool = False,
        cache_info: Optional[CacheInfo] = None,
        confidence: float = 0.0,
    ) -> TaskSchedulerReport:
        conf_level = (
            CONFIDENCE_HIGH if confidence >= CONFIDENCE_HIGH_THRESHOLD
            else CONFIDENCE_MEDIUM if confidence >= CONFIDENCE_MEDIUM_THRESHOLD
            else CONFIDENCE_LOW
        )
        report = TaskSchedulerReport(
            report_id=str(uuid.uuid4()),
            tasks=tasks,
            events=events,
            retries=retries,
            stats=stats,
            findings=[],
            task_count=len(tasks),
            completed_count=sum(1 for t in tasks if t.state == STATE_COMPLETED),
            failed_count=sum(1 for t in tasks if t.state == STATE_FAILED),
            cancelled_count=sum(1 for t in tasks if t.state == STATE_CANCELLED),
            dependency_violations=dependency_violations,
            early_start_violations=early_start_violations,
            load_throttled=load_throttled,
            policy=policy,
            self_verification_passed=self_verification_passed,
            readiness_status=VERDICT_NOT_READY,
            verdict=VERDICT_NOT_READY,
            cache_info=cache_info or CacheInfo(),
            provenance=SchedulerProvenance(
                engine_name="task_scheduler",
                engine_version="1.0.0",
                sources_used=list(sources_used),
                sources_missing=list(sources_missing),
                generated_at=datetime.now(timezone.utc).isoformat(),
                confidence=confidence,
                confidence_level=conf_level,
                self_verification_passed=self_verification_passed,
            ),
            is_empty=len(tasks) == 0,
        )
        _log.info(
            "BlueprintBuilder produced %s (tasks=%d completed=%d failed=%d)",
            report.report_id[:8], len(tasks), report.completed_count, report.failed_count,
        )
        return report


__all__ = ["BlueprintBuilder"]
