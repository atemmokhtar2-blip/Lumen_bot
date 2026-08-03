"""BlueprintBuilder — Specification 023"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import List, Optional

from .report_data import (
    InterfaceContractBlueprint,
    InterfaceDescriptor,
    InterfaceContract,
    CommunicationRule,
    DependencyRule,
    InterfaceConflict,
    CacheInfo,
    InterfaceProvenance,
    CONFIDENCE_HIGH,
    CONFIDENCE_MEDIUM,
    CONFIDENCE_LOW,
    CONFIDENCE_HIGH_THRESHOLD,
    CONFIDENCE_MEDIUM_THRESHOLD,
    VERDICT_NOT_READY,
)

_log = logging.getLogger("engine.interface_contract_planning.blueprint_builder")


class BlueprintBuilder:
    def build(
        self,
        interfaces: List[InterfaceDescriptor],
        contracts: List[InterfaceContract],
        communication_rules: List[CommunicationRule],
        dependency_rules: List[DependencyRule],
        conflicts: List[InterfaceConflict],
        sources_used: List[str],
        sources_missing: List[str],
        cache_info: Optional[CacheInfo] = None,
        confidence: float = 0.0,
    ) -> InterfaceContractBlueprint:
        conf_level = (
            CONFIDENCE_HIGH if confidence >= CONFIDENCE_HIGH_THRESHOLD
            else CONFIDENCE_MEDIUM if confidence >= CONFIDENCE_MEDIUM_THRESHOLD
            else CONFIDENCE_LOW
        )
        bp = InterfaceContractBlueprint(
            blueprint_id=str(uuid.uuid4()),
            interfaces=interfaces,
            contracts=contracts,
            communication_rules=communication_rules,
            dependency_rules=dependency_rules,
            conflicts=conflicts,
            findings=[],
            readiness_status=VERDICT_NOT_READY,
            verdict=VERDICT_NOT_READY,
            cache_info=cache_info or CacheInfo(),
            provenance=InterfaceProvenance(
                engine_name="interface_contract_planning",
                engine_version="1.0.0",
                sources_used=list(sources_used),
                sources_missing=list(sources_missing),
                generated_at=datetime.now(timezone.utc).isoformat(),
                confidence=confidence,
                confidence_level=conf_level,
            ),
            is_empty=len(interfaces) == 0,
        )
        _log.info("BlueprintBuilder produced %s (%d interfaces)", bp.blueprint_id[:8], len(interfaces))
        return bp


__all__ = ["BlueprintBuilder"]
