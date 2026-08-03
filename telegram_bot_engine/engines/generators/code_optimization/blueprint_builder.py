"""BlueprintBuilder — Specification 034"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import List, Optional

from .report_data import (
    CodeOptimizationReport, OptimizedUnit, OptimizationAction, OptimizationIssue,
    CacheInfo, OptimizationProvenance,
    CONFIDENCE_HIGH, CONFIDENCE_MEDIUM, CONFIDENCE_LOW,
    CONFIDENCE_HIGH_THRESHOLD, CONFIDENCE_MEDIUM_THRESHOLD, VERDICT_NOT_READY,
)

_log = logging.getLogger("engine.code_optimization.blueprint_builder")


class BlueprintBuilder:
    def build(
        self,
        units: List[OptimizedUnit],
        actions: List[OptimizationAction],
        issues: List[OptimizationIssue],
        sources_used: List[str],
        sources_missing: List[str],
        cache_info: Optional[CacheInfo] = None,
        confidence: float = 0.0,
    ) -> CodeOptimizationReport:
        conf_level = (
            CONFIDENCE_HIGH if confidence >= CONFIDENCE_HIGH_THRESHOLD
            else CONFIDENCE_MEDIUM if confidence >= CONFIDENCE_MEDIUM_THRESHOLD
            else CONFIDENCE_LOW
        )
        avg_before = (
            round(sum(u.quality_before for u in units) / len(units), 1) if units else 0.0
        )
        avg_after = (
            round(sum(u.quality_after for u in units) / len(units), 1) if units else 0.0
        )
        lines_saved = sum(max(0, u.lines_before - u.lines_after) for u in units)

        report = CodeOptimizationReport(
            report_id=str(uuid.uuid4()),
            units=units,
            actions=actions,
            issues=issues,
            findings=[],
            unit_count=len(units),
            action_count=len(actions),
            average_quality_before=avg_before,
            average_quality_after=avg_after,
            lines_saved=lines_saved,
            readiness_status=VERDICT_NOT_READY,
            verdict=VERDICT_NOT_READY,
            cache_info=cache_info or CacheInfo(),
            provenance=OptimizationProvenance(
                engine_name="code_optimization",
                engine_version="1.0.0",
                sources_used=list(sources_used),
                sources_missing=list(sources_missing),
                generated_at=datetime.now(timezone.utc).isoformat(),
                confidence=confidence,
                confidence_level=conf_level,
            ),
            is_empty=len(units) == 0,
        )
        _log.info(
            "BlueprintBuilder produced %s (%d units, %d actions, lines_saved=%d)",
            report.report_id[:8], len(units), len(actions), lines_saved,
        )
        return report


__all__ = ["BlueprintBuilder"]
