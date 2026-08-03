"""BlueprintBuilder — Specification 026"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import List, Optional

from .report_data import (
    GenerationStrategyBlueprint, GenerationStage, GenerationItem,
    GenerationRule, RollbackPoint, OptimizationStep, StrategyConflict,
    CacheInfo, StrategyProvenance,
    CONFIDENCE_HIGH, CONFIDENCE_MEDIUM, CONFIDENCE_LOW,
    CONFIDENCE_HIGH_THRESHOLD, CONFIDENCE_MEDIUM_THRESHOLD, VERDICT_NOT_READY,
)

_log = logging.getLogger("engine.generation_strategy.blueprint_builder")


class BlueprintBuilder:
    def build(
        self,
        stages: List[GenerationStage],
        items: List[GenerationItem],
        generation_order: List[str],
        rules: List[GenerationRule],
        rollback_points: List[RollbackPoint],
        optimizations: List[OptimizationStep],
        conflicts: List[StrategyConflict],
        sources_used: List[str],
        sources_missing: List[str],
        cache_info: Optional[CacheInfo] = None,
        confidence: float = 0.0,
    ) -> GenerationStrategyBlueprint:
        conf_level = (
            CONFIDENCE_HIGH if confidence >= CONFIDENCE_HIGH_THRESHOLD
            else CONFIDENCE_MEDIUM if confidence >= CONFIDENCE_MEDIUM_THRESHOLD
            else CONFIDENCE_LOW
        )
        bp = GenerationStrategyBlueprint(
            blueprint_id=str(uuid.uuid4()),
            stages=stages,
            items=items,
            generation_order=generation_order,
            rules=rules,
            rollback_points=rollback_points,
            optimizations=optimizations,
            conflicts=conflicts,
            findings=[],
            readiness_status=VERDICT_NOT_READY,
            verdict=VERDICT_NOT_READY,
            cache_info=cache_info or CacheInfo(),
            provenance=StrategyProvenance(
                engine_name="generation_strategy",
                engine_version="1.0.0",
                sources_used=list(sources_used),
                sources_missing=list(sources_missing),
                generated_at=datetime.now(timezone.utc).isoformat(),
                confidence=confidence,
                confidence_level=conf_level,
            ),
            is_empty=len(items) == 0,
        )
        _log.info("BlueprintBuilder produced %s (%d items)", bp.blueprint_id[:8], len(items))
        return bp


__all__ = ["BlueprintBuilder"]
