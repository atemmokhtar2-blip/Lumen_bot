"""BlueprintBuilder — Specification 029 v2.0"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import List, Optional

from .report_data import (
    IntelligentCodeGenerationPlan, GenerationContext, GenerationUnit,
    QueueEntry, GenerationRule, StyleRules, SimulationReport, RollbackPoint,
    IntelligenceScore, PlanConflict, CacheInfo, PlanProvenance,
    CONFIDENCE_HIGH, CONFIDENCE_MEDIUM, CONFIDENCE_LOW,
    CONFIDENCE_HIGH_THRESHOLD, CONFIDENCE_MEDIUM_THRESHOLD, VERDICT_NOT_READY,
)

_log = logging.getLogger("engine.code_generation_planning.blueprint_builder")


class BlueprintBuilder:
    def build(
        self,
        context: GenerationContext,
        units: List[GenerationUnit],
        queue: List[QueueEntry],
        generation_order: List[str],
        rules: List[GenerationRule],
        style: StyleRules,
        simulation: SimulationReport,
        rollback_points: List[RollbackPoint],
        intelligence_scores: List[IntelligenceScore],
        overall_score: float,
        conflicts: List[PlanConflict],
        sources_used: List[str],
        sources_missing: List[str],
        cache_info: Optional[CacheInfo] = None,
        confidence: float = 0.0,
    ) -> IntelligentCodeGenerationPlan:
        conf_level = (
            CONFIDENCE_HIGH if confidence >= CONFIDENCE_HIGH_THRESHOLD
            else CONFIDENCE_MEDIUM if confidence >= CONFIDENCE_MEDIUM_THRESHOLD
            else CONFIDENCE_LOW
        )
        plan = IntelligentCodeGenerationPlan(
            plan_id=str(uuid.uuid4()),
            context=context,
            units=units,
            queue=queue,
            generation_order=generation_order,
            rules=rules,
            style=style,
            simulation=simulation,
            rollback_points=rollback_points,
            intelligence_scores=intelligence_scores,
            overall_intelligence_score=overall_score,
            conflicts=conflicts,
            findings=[],
            readiness_status=VERDICT_NOT_READY,
            verdict=VERDICT_NOT_READY,
            cache_info=cache_info or CacheInfo(),
            provenance=PlanProvenance(
                engine_name="code_generation_planning",
                engine_version="2.0.0",
                sources_used=list(sources_used),
                sources_missing=list(sources_missing),
                generated_at=datetime.now(timezone.utc).isoformat(),
                confidence=confidence,
                confidence_level=conf_level,
            ),
            is_empty=len(units) == 0,
        )
        _log.info(
            "BlueprintBuilder produced %s (units=%d score=%.1f)",
            plan.plan_id[:8], len(units), overall_score,
        )
        return plan


__all__ = ["BlueprintBuilder"]
