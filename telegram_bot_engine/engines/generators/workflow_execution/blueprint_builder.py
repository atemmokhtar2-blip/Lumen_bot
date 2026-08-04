"""BlueprintBuilder — Specification 064"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import List, Optional

from .report_data import (
    WorkflowExecutionReport, WorkflowStage, Checkpoint, WorkflowEvent,
    RollbackRecord, WorkflowStats, CacheInfo, WorkflowProvenance,
    CONFIDENCE_HIGH, CONFIDENCE_MEDIUM, CONFIDENCE_LOW,
    CONFIDENCE_HIGH_THRESHOLD, CONFIDENCE_MEDIUM_THRESHOLD, VERDICT_NOT_READY,
    STAGE_COMPLETED, STAGE_FAILED, STAGE_ROLLED_BACK,
)

_log = logging.getLogger("engine.workflow_execution.blueprint_builder")


class BlueprintBuilder:
    def build(
        self,
        workflow_id: str,
        stages: List[WorkflowStage],
        checkpoints: List[Checkpoint],
        events: List[WorkflowEvent],
        rollbacks: List[RollbackRecord],
        stats: WorkflowStats,
        sources_used: List[str],
        sources_missing: List[str],
        sequential_gate_violations: int = 0,
        resumed: bool = False,
        rolled_back: bool = False,
        self_verification_passed: bool = False,
        cache_info: Optional[CacheInfo] = None,
        confidence: float = 0.0,
    ) -> WorkflowExecutionReport:
        conf_level = (
            CONFIDENCE_HIGH if confidence >= CONFIDENCE_HIGH_THRESHOLD
            else CONFIDENCE_MEDIUM if confidence >= CONFIDENCE_MEDIUM_THRESHOLD
            else CONFIDENCE_LOW
        )
        report = WorkflowExecutionReport(
            report_id=str(uuid.uuid4()),
            workflow_id=workflow_id,
            stages=stages,
            checkpoints=checkpoints,
            events=events,
            rollbacks=rollbacks,
            stats=stats,
            findings=[],
            stage_count=len(stages),
            completed_count=sum(1 for s in stages if s.state == STAGE_COMPLETED),
            failed_count=sum(
                1 for s in stages if s.state in (STAGE_FAILED, STAGE_ROLLED_BACK)
            ),
            sequential_gate_violations=sequential_gate_violations,
            resumed=resumed,
            rolled_back=rolled_back,
            self_verification_passed=self_verification_passed,
            readiness_status=VERDICT_NOT_READY,
            verdict=VERDICT_NOT_READY,
            cache_info=cache_info or CacheInfo(),
            provenance=WorkflowProvenance(
                engine_name="workflow_execution",
                engine_version="1.0.0",
                sources_used=list(sources_used),
                sources_missing=list(sources_missing),
                generated_at=datetime.now(timezone.utc).isoformat(),
                confidence=confidence,
                confidence_level=conf_level,
                self_verification_passed=self_verification_passed,
            ),
            is_empty=len(stages) == 0,
        )
        _log.info(
            "BlueprintBuilder produced %s (stages=%d completed=%d cps=%d)",
            report.report_id[:8], len(stages), report.completed_count, len(checkpoints),
        )
        return report


__all__ = ["BlueprintBuilder"]
