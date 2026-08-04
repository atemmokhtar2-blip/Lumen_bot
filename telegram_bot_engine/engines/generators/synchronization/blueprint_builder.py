"""BlueprintBuilder — Specification 055"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import List, Optional

from .report_data import (
    SynchronizationReport, SyncEvent, ConflictRecord, Transaction,
    SyncHealth, CacheInfo, SyncProvenance,
    CONFIDENCE_HIGH, CONFIDENCE_MEDIUM, CONFIDENCE_LOW,
    CONFIDENCE_HIGH_THRESHOLD, CONFIDENCE_MEDIUM_THRESHOLD, VERDICT_NOT_READY,
)

_log = logging.getLogger("engine.synchronization.blueprint_builder")


class BlueprintBuilder:
    def build(
        self,
        events: List[SyncEvent],
        conflicts: List[ConflictRecord],
        transactions: List[Transaction],
        health: SyncHealth,
        sources_used: List[str],
        sources_missing: List[str],
        recovered: bool = False,
        consistent: bool = True,
        self_verification_passed: bool = False,
        cache_info: Optional[CacheInfo] = None,
        confidence: float = 0.0,
    ) -> SynchronizationReport:
        conf_level = (
            CONFIDENCE_HIGH if confidence >= CONFIDENCE_HIGH_THRESHOLD
            else CONFIDENCE_MEDIUM if confidence >= CONFIDENCE_MEDIUM_THRESHOLD
            else CONFIDENCE_LOW
        )
        unresolved = sum(1 for c in conflicts if not c.resolved)
        report = SynchronizationReport(
            report_id=str(uuid.uuid4()),
            events=events,
            conflicts=conflicts,
            transactions=transactions,
            health=health,
            findings=[],
            event_count=len(events),
            conflict_count=len(conflicts),
            unresolved_count=unresolved,
            recovered=recovered,
            consistent=consistent,
            self_verification_passed=self_verification_passed,
            readiness_status=VERDICT_NOT_READY,
            verdict=VERDICT_NOT_READY,
            cache_info=cache_info or CacheInfo(),
            provenance=SyncProvenance(
                engine_name="synchronization",
                engine_version="1.0.0",
                sources_used=list(sources_used),
                sources_missing=list(sources_missing),
                generated_at=datetime.now(timezone.utc).isoformat(),
                confidence=confidence,
                confidence_level=conf_level,
                self_verification_passed=self_verification_passed,
            ),
            is_empty=len(events) == 0 and len(conflicts) == 0,
        )
        _log.info(
            "BlueprintBuilder produced %s (events=%d conflicts=%d consistent=%s)",
            report.report_id[:8], len(events), len(conflicts), consistent,
        )
        return report


__all__ = ["BlueprintBuilder"]
