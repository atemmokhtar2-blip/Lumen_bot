"""BlueprintBuilder — Specification 042"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import List, Optional

from .report_data import (
    IntegrationVerificationReport, IntegrationCheck, CompatibilityItem,
    DependencyLink, IntegrationScore, CacheInfo, IntegrationProvenance,
    STATUS_FAILED, STATUS_WARNING,
    CONFIDENCE_HIGH, CONFIDENCE_MEDIUM, CONFIDENCE_LOW,
    CONFIDENCE_HIGH_THRESHOLD, CONFIDENCE_MEDIUM_THRESHOLD, VERDICT_NOT_READY,
)

_log = logging.getLogger("engine.integration_verification.blueprint_builder")


class BlueprintBuilder:
    def build(
        self,
        checks: List[IntegrationCheck],
        compatibility: List[CompatibilityItem],
        dependencies: List[DependencyLink],
        score: IntegrationScore,
        sources_used: List[str],
        sources_missing: List[str],
        self_verification_passed: bool = False,
        runs_completed: int = 0,
        cache_info: Optional[CacheInfo] = None,
        confidence: float = 0.0,
    ) -> IntegrationVerificationReport:
        conf_level = (
            CONFIDENCE_HIGH if confidence >= CONFIDENCE_HIGH_THRESHOLD
            else CONFIDENCE_MEDIUM if confidence >= CONFIDENCE_MEDIUM_THRESHOLD
            else CONFIDENCE_LOW
        )
        failed = sum(1 for c in checks if c.status == STATUS_FAILED)
        warnings = sum(1 for c in checks if c.status == STATUS_WARNING)
        report = IntegrationVerificationReport(
            report_id=str(uuid.uuid4()),
            checks=checks,
            compatibility=compatibility,
            dependencies=dependencies,
            score=score,
            findings=[],
            check_count=len(checks),
            failed_count=failed,
            warning_count=warnings,
            self_verification_passed=self_verification_passed,
            readiness_status=VERDICT_NOT_READY,
            verdict=VERDICT_NOT_READY,
            cache_info=cache_info or CacheInfo(),
            provenance=IntegrationProvenance(
                engine_name="integration_verification",
                engine_version="1.0.0",
                sources_used=list(sources_used),
                sources_missing=list(sources_missing),
                generated_at=datetime.now(timezone.utc).isoformat(),
                confidence=confidence,
                confidence_level=conf_level,
                self_verification_passed=self_verification_passed,
                runs_completed=runs_completed,
            ),
            is_empty=len(checks) == 0,
        )
        _log.info(
            "BlueprintBuilder produced %s (checks=%d failed=%d score=%.1f)",
            report.report_id[:8], len(checks), failed, score.overall,
        )
        return report


__all__ = ["BlueprintBuilder"]
