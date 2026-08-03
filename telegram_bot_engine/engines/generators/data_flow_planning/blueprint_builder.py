"""BlueprintBuilder — Specification 024"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import List, Optional

from .report_data import (
    DataFlowBlueprint, DataSource, DataDestination, DataFlowPath,
    ValidationRule, SecurityRule, ErrorFlow, DataFlowConflict,
    CacheInfo, DataFlowProvenance,
    CONFIDENCE_HIGH, CONFIDENCE_MEDIUM, CONFIDENCE_LOW,
    CONFIDENCE_HIGH_THRESHOLD, CONFIDENCE_MEDIUM_THRESHOLD, VERDICT_NOT_READY,
)

_log = logging.getLogger("engine.data_flow_planning.blueprint_builder")


class BlueprintBuilder:
    def build(
        self,
        sources: List[DataSource],
        destinations: List[DataDestination],
        paths: List[DataFlowPath],
        validation_rules: List[ValidationRule],
        security_rules: List[SecurityRule],
        error_flows: List[ErrorFlow],
        conflicts: List[DataFlowConflict],
        sources_used: List[str],
        sources_missing: List[str],
        cache_info: Optional[CacheInfo] = None,
        confidence: float = 0.0,
    ) -> DataFlowBlueprint:
        conf_level = (
            CONFIDENCE_HIGH if confidence >= CONFIDENCE_HIGH_THRESHOLD
            else CONFIDENCE_MEDIUM if confidence >= CONFIDENCE_MEDIUM_THRESHOLD
            else CONFIDENCE_LOW
        )
        bp = DataFlowBlueprint(
            blueprint_id=str(uuid.uuid4()),
            sources=sources,
            destinations=destinations,
            paths=paths,
            validation_rules=validation_rules,
            security_rules=security_rules,
            error_flows=error_flows,
            conflicts=conflicts,
            findings=[],
            readiness_status=VERDICT_NOT_READY,
            verdict=VERDICT_NOT_READY,
            cache_info=cache_info or CacheInfo(),
            provenance=DataFlowProvenance(
                engine_name="data_flow_planning",
                engine_version="1.0.0",
                sources_used=list(sources_used),
                sources_missing=list(sources_missing),
                generated_at=datetime.now(timezone.utc).isoformat(),
                confidence=confidence,
                confidence_level=conf_level,
            ),
            is_empty=len(paths) == 0,
        )
        _log.info("BlueprintBuilder produced %s (%d paths)", bp.blueprint_id[:8], len(paths))
        return bp


__all__ = ["BlueprintBuilder"]
