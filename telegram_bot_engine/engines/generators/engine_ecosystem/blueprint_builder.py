"""BlueprintBuilder — Specification 052"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import List, Optional

from .report_data import (
    EngineEcosystemReport, EngineManifest, DependencyEdge, CapabilityEntry,
    CompatibilityResult, EngineHealth, CacheInfo, EcosystemProvenance,
    HEALTH_ISOLATED,
    CONFIDENCE_HIGH, CONFIDENCE_MEDIUM, CONFIDENCE_LOW,
    CONFIDENCE_HIGH_THRESHOLD, CONFIDENCE_MEDIUM_THRESHOLD, VERDICT_NOT_READY,
)

_log = logging.getLogger("engine.engine_ecosystem.blueprint_builder")


class BlueprintBuilder:
    def build(
        self,
        manifests: List[EngineManifest],
        edges: List[DependencyEdge],
        capabilities: List[CapabilityEntry],
        compatibility: List[CompatibilityResult],
        health: List[EngineHealth],
        sources_used: List[str],
        sources_missing: List[str],
        self_verification_passed: bool = False,
        cache_info: Optional[CacheInfo] = None,
        confidence: float = 0.0,
    ) -> EngineEcosystemReport:
        conf_level = (
            CONFIDENCE_HIGH if confidence >= CONFIDENCE_HIGH_THRESHOLD
            else CONFIDENCE_MEDIUM if confidence >= CONFIDENCE_MEDIUM_THRESHOLD
            else CONFIDENCE_LOW
        )
        conflicts = sum(1 for c in compatibility if not c.compatible)
        isolated = sum(1 for h in health if h.isolated or h.status == HEALTH_ISOLATED)
        report = EngineEcosystemReport(
            report_id=str(uuid.uuid4()),
            manifests=manifests,
            edges=edges,
            capabilities=capabilities,
            compatibility=compatibility,
            health=health,
            findings=[],
            engine_count=len(manifests),
            conflict_count=conflicts,
            isolated_count=isolated,
            self_verification_passed=self_verification_passed,
            readiness_status=VERDICT_NOT_READY,
            verdict=VERDICT_NOT_READY,
            cache_info=cache_info or CacheInfo(),
            provenance=EcosystemProvenance(
                engine_name="engine_ecosystem",
                engine_version="1.0.0",
                sources_used=list(sources_used),
                sources_missing=list(sources_missing),
                generated_at=datetime.now(timezone.utc).isoformat(),
                confidence=confidence,
                confidence_level=conf_level,
                self_verification_passed=self_verification_passed,
            ),
            is_empty=len(manifests) == 0,
        )
        _log.info(
            "BlueprintBuilder produced %s (engines=%d conflicts=%d isolated=%d)",
            report.report_id[:8], len(manifests), conflicts, isolated,
        )
        return report


__all__ = ["BlueprintBuilder"]
