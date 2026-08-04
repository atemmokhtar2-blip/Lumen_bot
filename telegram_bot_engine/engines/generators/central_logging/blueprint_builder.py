"""BlueprintBuilder — Specification 058"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import List, Optional

from .report_data import (
    CentralLoggingReport, LogEntry, AuditRecord, SearchReport,
    IntegrityReport, ArchiveRecord, CacheInfo, LoggingProvenance,
    CONFIDENCE_HIGH, CONFIDENCE_MEDIUM, CONFIDENCE_LOW,
    CONFIDENCE_HIGH_THRESHOLD, CONFIDENCE_MEDIUM_THRESHOLD, VERDICT_NOT_READY,
)

_log = logging.getLogger("engine.central_logging.blueprint_builder")


class BlueprintBuilder:
    def build(
        self,
        entries: List[LogEntry],
        audit_trail: List[AuditRecord],
        search: SearchReport,
        integrity: IntegrityReport,
        archives: List[ArchiveRecord],
        sources_used: List[str],
        sources_missing: List[str],
        redacted_count: int = 0,
        rotated: bool = False,
        external_log_violations: int = 0,
        self_verification_passed: bool = False,
        cache_info: Optional[CacheInfo] = None,
        confidence: float = 0.0,
    ) -> CentralLoggingReport:
        conf_level = (
            CONFIDENCE_HIGH if confidence >= CONFIDENCE_HIGH_THRESHOLD
            else CONFIDENCE_MEDIUM if confidence >= CONFIDENCE_MEDIUM_THRESHOLD
            else CONFIDENCE_LOW
        )
        report = CentralLoggingReport(
            report_id=str(uuid.uuid4()),
            entries=entries,
            audit_trail=audit_trail,
            search=search,
            integrity=integrity,
            archives=archives,
            findings=[],
            entry_count=len(entries),
            audit_count=len(audit_trail),
            redacted_count=redacted_count,
            rotated=rotated,
            external_log_violations=external_log_violations,
            self_verification_passed=self_verification_passed,
            readiness_status=VERDICT_NOT_READY,
            verdict=VERDICT_NOT_READY,
            cache_info=cache_info or CacheInfo(),
            provenance=LoggingProvenance(
                engine_name="central_logging",
                engine_version="1.0.0",
                sources_used=list(sources_used),
                sources_missing=list(sources_missing),
                generated_at=datetime.now(timezone.utc).isoformat(),
                confidence=confidence,
                confidence_level=conf_level,
                self_verification_passed=self_verification_passed,
            ),
            is_empty=len(entries) == 0,
        )
        _log.info(
            "BlueprintBuilder produced %s (entries=%d audit=%d redacted=%d)",
            report.report_id[:8], len(entries), len(audit_trail), redacted_count,
        )
        return report


__all__ = ["BlueprintBuilder"]
