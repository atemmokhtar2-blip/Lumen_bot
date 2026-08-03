"""BlueprintBuilder — Specification 033"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import List, Optional

from .report_data import (
    BusinessLogicReport, LogicBody, LogicIssue, OptimizationNote,
    CacheInfo, LogicProvenance,
    CONFIDENCE_HIGH, CONFIDENCE_MEDIUM, CONFIDENCE_LOW,
    CONFIDENCE_HIGH_THRESHOLD, CONFIDENCE_MEDIUM_THRESHOLD, VERDICT_NOT_READY,
)

_log = logging.getLogger("engine.business_logic_generation.blueprint_builder")


class BlueprintBuilder:
    def build(
        self,
        bodies: List[LogicBody],
        issues: List[LogicIssue],
        optimizations: List[OptimizationNote],
        sources_used: List[str],
        sources_missing: List[str],
        cache_info: Optional[CacheInfo] = None,
        confidence: float = 0.0,
    ) -> BusinessLogicReport:
        conf_level = (
            CONFIDENCE_HIGH if confidence >= CONFIDENCE_HIGH_THRESHOLD
            else CONFIDENCE_MEDIUM if confidence >= CONFIDENCE_MEDIUM_THRESHOLD
            else CONFIDENCE_LOW
        )
        avg = round(sum(b.quality_score for b in bodies) / len(bodies), 1) if bodies else 0.0
        report = BusinessLogicReport(
            report_id=str(uuid.uuid4()),
            bodies=bodies,
            issues=issues,
            findings=[],
            optimizations=optimizations,
            body_count=len(bodies),
            average_quality=avg,
            readiness_status=VERDICT_NOT_READY,
            verdict=VERDICT_NOT_READY,
            cache_info=cache_info or CacheInfo(),
            provenance=LogicProvenance(
                engine_name="business_logic_generation",
                engine_version="1.0.0",
                sources_used=list(sources_used),
                sources_missing=list(sources_missing),
                generated_at=datetime.now(timezone.utc).isoformat(),
                confidence=confidence,
                confidence_level=conf_level,
            ),
            is_empty=len(bodies) == 0,
        )
        _log.info(
            "BlueprintBuilder produced %s (%d bodies, avg_quality=%.1f)",
            report.report_id[:8], len(bodies), avg,
        )
        return report


__all__ = ["BlueprintBuilder"]
