"""BlueprintBuilder — Specification 025"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import List, Optional

from .report_data import (
    ResourceDependencyBlueprint, DependencyItem, ResourceItem,
    VersionMatrixEntry, RiskItem, OptimizationSuggestion, ResourceConflict,
    CacheInfo, ResourceProvenance,
    CONFIDENCE_HIGH, CONFIDENCE_MEDIUM, CONFIDENCE_LOW,
    CONFIDENCE_HIGH_THRESHOLD, CONFIDENCE_MEDIUM_THRESHOLD, VERDICT_NOT_READY,
)

_log = logging.getLogger("engine.resource_dependency_planning.blueprint_builder")


class BlueprintBuilder:
    def build(
        self,
        dependencies: List[DependencyItem],
        resources: List[ResourceItem],
        version_matrix: List[VersionMatrixEntry],
        risks: List[RiskItem],
        optimizations: List[OptimizationSuggestion],
        conflicts: List[ResourceConflict],
        python_version: str,
        sources_used: List[str],
        sources_missing: List[str],
        cache_info: Optional[CacheInfo] = None,
        confidence: float = 0.0,
    ) -> ResourceDependencyBlueprint:
        conf_level = (
            CONFIDENCE_HIGH if confidence >= CONFIDENCE_HIGH_THRESHOLD
            else CONFIDENCE_MEDIUM if confidence >= CONFIDENCE_MEDIUM_THRESHOLD
            else CONFIDENCE_LOW
        )
        bp = ResourceDependencyBlueprint(
            blueprint_id=str(uuid.uuid4()),
            dependencies=dependencies,
            resources=resources,
            version_matrix=version_matrix,
            risks=risks,
            optimizations=optimizations,
            conflicts=conflicts,
            findings=[],
            python_version=python_version,
            readiness_status=VERDICT_NOT_READY,
            verdict=VERDICT_NOT_READY,
            cache_info=cache_info or CacheInfo(),
            provenance=ResourceProvenance(
                engine_name="resource_dependency_planning",
                engine_version="1.0.0",
                sources_used=list(sources_used),
                sources_missing=list(sources_missing),
                generated_at=datetime.now(timezone.utc).isoformat(),
                confidence=confidence,
                confidence_level=conf_level,
            ),
            is_empty=len(dependencies) == 0,
        )
        _log.info("BlueprintBuilder produced %s (%d deps)", bp.blueprint_id[:8], len(dependencies))
        return bp


__all__ = ["BlueprintBuilder"]
