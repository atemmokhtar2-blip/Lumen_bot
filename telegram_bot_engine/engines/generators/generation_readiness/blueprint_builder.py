"""BlueprintBuilder — Specification 027"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import List, Optional

from .report_data import (
    GenerationReadinessReport, CategoryScore, ValidationIssue, MissingItem,
    CacheInfo, ReadinessProvenance,
    CONFIDENCE_HIGH, CONFIDENCE_MEDIUM, CONFIDENCE_LOW,
    CONFIDENCE_HIGH_THRESHOLD, CONFIDENCE_MEDIUM_THRESHOLD,
    VERDICT_NOT_READY, APPROVAL_PENDING,
)

_log = logging.getLogger("engine.generation_readiness.blueprint_builder")


class BlueprintBuilder:
    def build(
        self,
        category_scores: List[CategoryScore],
        overall_score: float,
        issues: List[ValidationIssue],
        missing_items: List[MissingItem],
        sources_used: List[str],
        sources_missing: List[str],
        cache_info: Optional[CacheInfo] = None,
        confidence: float = 0.0,
    ) -> GenerationReadinessReport:
        conf_level = (
            CONFIDENCE_HIGH if confidence >= CONFIDENCE_HIGH_THRESHOLD
            else CONFIDENCE_MEDIUM if confidence >= CONFIDENCE_MEDIUM_THRESHOLD
            else CONFIDENCE_LOW
        )
        report = GenerationReadinessReport(
            report_id=str(uuid.uuid4()),
            category_scores=category_scores,
            overall_score=overall_score,
            issues=issues,
            missing_items=missing_items,
            findings=[],
            approval_status=APPROVAL_PENDING,
            readiness_status=VERDICT_NOT_READY,
            verdict=VERDICT_NOT_READY,
            cache_info=cache_info or CacheInfo(),
            provenance=ReadinessProvenance(
                engine_name="generation_readiness",
                engine_version="1.0.0",
                sources_used=list(sources_used),
                sources_missing=list(sources_missing),
                generated_at=datetime.now(timezone.utc).isoformat(),
                confidence=confidence,
                confidence_level=conf_level,
            ),
            is_empty=False,
        )
        _log.info("BlueprintBuilder produced %s (score=%.1f)", report.report_id[:8], overall_score)
        return report


__all__ = ["BlueprintBuilder"]
