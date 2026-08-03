"""BlueprintBuilder — Specification 028"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import List, Optional

from .report_data import (
    GenerationSessionReport, GenerationTask, Checkpoint, SessionLogEntry,
    ProgressInfo, CacheInfo, OrchestratorProvenance,
    STATUS_PENDING, STATUS_RUNNING,
    CONFIDENCE_HIGH, CONFIDENCE_MEDIUM, CONFIDENCE_LOW,
    CONFIDENCE_HIGH_THRESHOLD, CONFIDENCE_MEDIUM_THRESHOLD, VERDICT_NOT_READY,
)

_log = logging.getLogger("engine.generation_orchestrator.blueprint_builder")


class BlueprintBuilder:
    def build(
        self,
        session_id: str,
        project_id: str,
        tasks: List[GenerationTask],
        checkpoints: List[Checkpoint],
        logs: List[SessionLogEntry],
        progress: ProgressInfo,
        readiness_approved: bool,
        readiness_score: float,
        sources_used: List[str],
        sources_missing: List[str],
        cache_info: Optional[CacheInfo] = None,
        confidence: float = 0.0,
    ) -> GenerationSessionReport:
        conf_level = (
            CONFIDENCE_HIGH if confidence >= CONFIDENCE_HIGH_THRESHOLD
            else CONFIDENCE_MEDIUM if confidence >= CONFIDENCE_MEDIUM_THRESHOLD
            else CONFIDENCE_LOW
        )
        now = datetime.now(timezone.utc).isoformat()
        report = GenerationSessionReport(
            session_id=session_id,
            project_id=project_id,
            status=STATUS_RUNNING if readiness_approved else STATUS_PENDING,
            current_phase=progress.current_phase,
            started_at=now,
            finished_at="",
            tasks=tasks,
            checkpoints=checkpoints,
            logs=logs,
            progress=progress,
            findings=[],
            readiness_approved=readiness_approved,
            readiness_score=readiness_score,
            readiness_status=VERDICT_NOT_READY,
            verdict=VERDICT_NOT_READY,
            cache_info=cache_info or CacheInfo(),
            provenance=OrchestratorProvenance(
                engine_name="generation_orchestrator",
                engine_version="1.0.0",
                sources_used=list(sources_used),
                sources_missing=list(sources_missing),
                generated_at=now,
                confidence=confidence,
                confidence_level=conf_level,
            ),
            is_empty=len(tasks) == 0,
        )
        _log.info(
            "BlueprintBuilder produced session=%s tasks=%d",
            session_id[:8], len(tasks),
        )
        return report


__all__ = ["BlueprintBuilder"]
