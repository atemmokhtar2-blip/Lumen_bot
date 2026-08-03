"""BlueprintBuilder — Specification 031"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import List, Optional

from .report_data import (
    ClassGenerationReport, ClassSkeleton, ClassConflict,
    CacheInfo, ClassProvenance,
    CONFIDENCE_HIGH, CONFIDENCE_MEDIUM, CONFIDENCE_LOW,
    CONFIDENCE_HIGH_THRESHOLD, CONFIDENCE_MEDIUM_THRESHOLD, VERDICT_NOT_READY,
)

_log = logging.getLogger("engine.class_generation.blueprint_builder")


class BlueprintBuilder:
    def build(
        self,
        classes: List[ClassSkeleton],
        conflicts: List[ClassConflict],
        sources_used: List[str],
        sources_missing: List[str],
        cache_info: Optional[CacheInfo] = None,
        confidence: float = 0.0,
    ) -> ClassGenerationReport:
        conf_level = (
            CONFIDENCE_HIGH if confidence >= CONFIDENCE_HIGH_THRESHOLD
            else CONFIDENCE_MEDIUM if confidence >= CONFIDENCE_MEDIUM_THRESHOLD
            else CONFIDENCE_LOW
        )
        report = ClassGenerationReport(
            report_id=str(uuid.uuid4()),
            classes=classes,
            conflicts=conflicts,
            findings=[],
            class_count=len(classes),
            readiness_status=VERDICT_NOT_READY,
            verdict=VERDICT_NOT_READY,
            cache_info=cache_info or CacheInfo(),
            provenance=ClassProvenance(
                engine_name="class_generation",
                engine_version="1.0.0",
                sources_used=list(sources_used),
                sources_missing=list(sources_missing),
                generated_at=datetime.now(timezone.utc).isoformat(),
                confidence=confidence,
                confidence_level=conf_level,
            ),
            is_empty=len(classes) == 0,
        )
        _log.info("BlueprintBuilder produced %s (%d classes)", report.report_id[:8], len(classes))
        return report


__all__ = ["BlueprintBuilder"]
