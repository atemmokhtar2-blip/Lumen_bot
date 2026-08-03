"""BlueprintBuilder — Specification 032"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Dict, List, Optional

from .report_data import (
    FunctionGenerationReport, MethodSkeleton, MethodConflict,
    CacheInfo, MethodProvenance,
    CONFIDENCE_HIGH, CONFIDENCE_MEDIUM, CONFIDENCE_LOW,
    CONFIDENCE_HIGH_THRESHOLD, CONFIDENCE_MEDIUM_THRESHOLD, VERDICT_NOT_READY,
)

_log = logging.getLogger("engine.function_generation.blueprint_builder")


class BlueprintBuilder:
    def build(
        self,
        methods: List[MethodSkeleton],
        method_registry: Dict[str, List[str]],
        conflicts: List[MethodConflict],
        sources_used: List[str],
        sources_missing: List[str],
        cache_info: Optional[CacheInfo] = None,
        confidence: float = 0.0,
    ) -> FunctionGenerationReport:
        conf_level = (
            CONFIDENCE_HIGH if confidence >= CONFIDENCE_HIGH_THRESHOLD
            else CONFIDENCE_MEDIUM if confidence >= CONFIDENCE_MEDIUM_THRESHOLD
            else CONFIDENCE_LOW
        )
        report = FunctionGenerationReport(
            report_id=str(uuid.uuid4()),
            methods=methods,
            method_registry=method_registry,
            conflicts=conflicts,
            findings=[],
            method_count=len(methods),
            readiness_status=VERDICT_NOT_READY,
            verdict=VERDICT_NOT_READY,
            cache_info=cache_info or CacheInfo(),
            provenance=MethodProvenance(
                engine_name="function_generation",
                engine_version="1.0.0",
                sources_used=list(sources_used),
                sources_missing=list(sources_missing),
                generated_at=datetime.now(timezone.utc).isoformat(),
                confidence=confidence,
                confidence_level=conf_level,
            ),
            is_empty=len(methods) == 0,
        )
        _log.info("BlueprintBuilder produced %s (%d methods)", report.report_id[:8], len(methods))
        return report


__all__ = ["BlueprintBuilder"]
