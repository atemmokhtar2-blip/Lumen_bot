"""BlueprintBuilder — Specification 022"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Dict, List, Optional

from .report_data import (
    ComponentArchitectureBlueprint,
    ComponentDescriptor,
    ComponentRelation,
    ComponentInterface,
    ReuseOpportunity,
    ComponentConflict,
    CacheInfo,
    ComponentProvenance,
    CONFIDENCE_HIGH,
    CONFIDENCE_MEDIUM,
    CONFIDENCE_LOW,
    CONFIDENCE_HIGH_THRESHOLD,
    CONFIDENCE_MEDIUM_THRESHOLD,
    VERDICT_NOT_READY,
)

_log = logging.getLogger("engine.component_architecture_planning.blueprint_builder")


class BlueprintBuilder:
    def build(
        self,
        components: List[ComponentDescriptor],
        relations: List[ComponentRelation],
        conflicts: List[ComponentConflict],
        reuses: List[ReuseOpportunity],
        dependency_graph: Dict[str, List[str]],
        sources_used: List[str],
        sources_missing: List[str],
        cache_info: Optional[CacheInfo] = None,
        confidence: float = 0.0,
    ) -> ComponentArchitectureBlueprint:
        conf_level = (
            CONFIDENCE_HIGH if confidence >= CONFIDENCE_HIGH_THRESHOLD
            else CONFIDENCE_MEDIUM if confidence >= CONFIDENCE_MEDIUM_THRESHOLD
            else CONFIDENCE_LOW
        )
        all_ifaces: List[ComponentInterface] = []
        for c in components:
            all_ifaces.extend(c.interfaces)

        comm_map: Dict[str, List[str]] = {}
        for r in relations:
            comm_map.setdefault(r.from_component_id, []).append(r.to_component_id)

        bp = ComponentArchitectureBlueprint(
            blueprint_id=str(uuid.uuid4()),
            components=components,
            relations=relations,
            interfaces=all_ifaces,
            reuse_opportunities=reuses,
            conflicts=conflicts,
            findings=[],
            communication_map=comm_map,
            dependency_graph=dependency_graph,
            readiness_status=VERDICT_NOT_READY,
            verdict=VERDICT_NOT_READY,
            cache_info=cache_info or CacheInfo(),
            provenance=ComponentProvenance(
                engine_name="component_architecture_planning",
                engine_version="1.0.0",
                sources_used=list(sources_used),
                sources_missing=list(sources_missing),
                generated_at=datetime.now(timezone.utc).isoformat(),
                confidence=confidence,
                confidence_level=conf_level,
            ),
            is_empty=len(components) == 0,
        )
        _log.info("BlueprintBuilder produced %s (%d components)", bp.blueprint_id[:8], len(components))
        return bp


__all__ = ["BlueprintBuilder"]
