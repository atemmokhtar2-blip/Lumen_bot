"""BlueprintBuilder — Specification 054"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import List, Optional

from .report_data import (
    ExecutionContextReport, ContextVersion, ContextLock, ContextChange,
    ValidationIssue, CacheInfo, ContextProvenance,
    CTX_ACTIVE,
    CONFIDENCE_HIGH, CONFIDENCE_MEDIUM, CONFIDENCE_LOW,
    CONFIDENCE_HIGH_THRESHOLD, CONFIDENCE_MEDIUM_THRESHOLD, VERDICT_NOT_READY,
)

_log = logging.getLogger("engine.execution_context.blueprint_builder")


class BlueprintBuilder:
    def build(
        self,
        context_id: str,
        project_id: str,
        status: str,
        version: int,
        versions: List[ContextVersion],
        locks: List[ContextLock],
        changes: List[ContextChange],
        validation_issues: List[ValidationIssue],
        shared_keys: List[str],
        sources_used: List[str],
        sources_missing: List[str],
        active_count: int = 1,
        isolated: bool = True,
        recovered: bool = False,
        self_verification_passed: bool = False,
        cache_info: Optional[CacheInfo] = None,
        confidence: float = 0.0,
    ) -> ExecutionContextReport:
        conf_level = (
            CONFIDENCE_HIGH if confidence >= CONFIDENCE_HIGH_THRESHOLD
            else CONFIDENCE_MEDIUM if confidence >= CONFIDENCE_MEDIUM_THRESHOLD
            else CONFIDENCE_LOW
        )
        report = ExecutionContextReport(
            report_id=str(uuid.uuid4()),
            context_id=context_id,
            project_id=project_id,
            status=status or CTX_ACTIVE,
            version=version,
            versions=versions,
            locks=locks,
            changes=changes,
            validation_issues=validation_issues,
            shared_keys=shared_keys,
            findings=[],
            active_count=active_count,
            isolated=isolated,
            recovered=recovered,
            self_verification_passed=self_verification_passed,
            readiness_status=VERDICT_NOT_READY,
            verdict=VERDICT_NOT_READY,
            cache_info=cache_info or CacheInfo(),
            provenance=ContextProvenance(
                engine_name="execution_context",
                engine_version="1.0.0",
                sources_used=list(sources_used),
                sources_missing=list(sources_missing),
                generated_at=datetime.now(timezone.utc).isoformat(),
                confidence=confidence,
                confidence_level=conf_level,
                self_verification_passed=self_verification_passed,
            ),
            is_empty=not context_id,
        )
        _log.info(
            "BlueprintBuilder produced %s (ctx=%s v=%d keys=%d isolated=%s)",
            report.report_id[:8], context_id[:8] if context_id else "-", version,
            len(shared_keys), isolated,
        )
        return report


__all__ = ["BlueprintBuilder"]
