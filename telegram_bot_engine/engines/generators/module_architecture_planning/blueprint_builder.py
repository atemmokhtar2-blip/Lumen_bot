"""BlueprintBuilder — Specification 021"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Dict, List, Optional

from .report_data import (
    ModuleArchitectureBlueprint,
    ModuleDescriptor,
    ModuleRelation,
    ModuleInterface,
    ArchitectureConflict,
    CacheInfo,
    ArchitectureProvenance,
    CONFIDENCE_HIGH,
    CONFIDENCE_MEDIUM,
    CONFIDENCE_LOW,
    CONFIDENCE_HIGH_THRESHOLD,
    CONFIDENCE_MEDIUM_THRESHOLD,
    VERDICT_NOT_READY,
)

_log = logging.getLogger("engine.module_architecture_planning.blueprint_builder")


class BlueprintBuilder:
    def build(
        self,
        modules: List[ModuleDescriptor],
        relations: List[ModuleRelation],
        conflicts: List[ArchitectureConflict],
        dependency_graph: Dict[str, List[str]],
        sources_used: List[str],
        sources_missing: List[str],
        cache_info: Optional[CacheInfo] = None,
        confidence: float = 0.0,
    ) -> ModuleArchitectureBlueprint:
        conf_level = (
            CONFIDENCE_HIGH if confidence >= CONFIDENCE_HIGH_THRESHOLD
            else CONFIDENCE_MEDIUM if confidence >= CONFIDENCE_MEDIUM_THRESHOLD
            else CONFIDENCE_LOW
        )
        all_ifaces: List[ModuleInterface] = []
        for m in modules:
            all_ifaces.extend(m.interfaces)

        bp = ModuleArchitectureBlueprint(
            blueprint_id=str(uuid.uuid4()),
            modules=modules,
            relations=relations,
            interfaces=all_ifaces,
            conflicts=conflicts,
            findings=[],
            dependency_graph=dependency_graph,
            readiness_status=VERDICT_NOT_READY,
            verdict=VERDICT_NOT_READY,
            cache_info=cache_info or CacheInfo(),
            provenance=ArchitectureProvenance(
                engine_name="module_architecture_planning",
                engine_version="1.0.0",
                sources_used=list(sources_used),
                sources_missing=list(sources_missing),
                generated_at=datetime.now(timezone.utc).isoformat(),
                confidence=confidence,
                confidence_level=conf_level,
            ),
            is_empty=len(modules) == 0,
        )
        _log.info("BlueprintBuilder produced blueprint %s (%d modules)", bp.blueprint_id[:8], len(modules))
        return bp


__all__ = ["BlueprintBuilder"]
