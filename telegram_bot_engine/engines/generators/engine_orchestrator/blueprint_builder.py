"""BlueprintBuilder — Specification 053"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import List, Optional

from .report_data import (
    EngineOrchestratorReport, PlannedTask, ExecutionRecord, ResourceAllocation,
    DeadlockInfo, PerformanceMetrics, CacheInfo, OrchestratorProvenance,
    TASK_FAILED,
    CONFIDENCE_HIGH, CONFIDENCE_MEDIUM, CONFIDENCE_LOW,
    CONFIDENCE_HIGH_THRESHOLD, CONFIDENCE_MEDIUM_THRESHOLD, VERDICT_NOT_READY,
)

_log = logging.getLogger("engine.engine_orchestrator.blueprint_builder")


class BlueprintBuilder:
    def build(
        self,
        plan: List[PlannedTask],
        history: List[ExecutionRecord],
        resources: List[ResourceAllocation],
        deadlocks: List[DeadlockInfo],
        metrics: PerformanceMetrics,
        sources_used: List[str],
        sources_missing: List[str],
        replanned: bool = False,
        self_verification_passed: bool = False,
        cache_info: Optional[CacheInfo] = None,
        confidence: float = 0.0,
    ) -> EngineOrchestratorReport:
        conf_level = (
            CONFIDENCE_HIGH if confidence >= CONFIDENCE_HIGH_THRESHOLD
            else CONFIDENCE_MEDIUM if confidence >= CONFIDENCE_MEDIUM_THRESHOLD
            else CONFIDENCE_LOW
        )
        failures = sum(1 for h in history if h.status == TASK_FAILED)
        report = EngineOrchestratorReport(
            report_id=str(uuid.uuid4()),
            plan=plan,
            history=history,
            resources=resources,
            deadlocks=deadlocks,
            metrics=metrics,
            findings=[],
            task_count=len(plan),
            failure_count=failures,
            deadlock_count=len(deadlocks),
            replanned=replanned,
            self_verification_passed=self_verification_passed,
            readiness_status=VERDICT_NOT_READY,
            verdict=VERDICT_NOT_READY,
            cache_info=cache_info or CacheInfo(),
            provenance=OrchestratorProvenance(
                engine_name="engine_orchestrator",
                engine_version="1.0.0",
                sources_used=list(sources_used),
                sources_missing=list(sources_missing),
                generated_at=datetime.now(timezone.utc).isoformat(),
                confidence=confidence,
                confidence_level=conf_level,
                self_verification_passed=self_verification_passed,
            ),
            is_empty=len(plan) == 0,
        )
        _log.info(
            "BlueprintBuilder produced %s (tasks=%d failures=%d waves=%d)",
            report.report_id[:8], len(plan), failures, metrics.parallel_waves,
        )
        return report


__all__ = ["BlueprintBuilder"]
