"""BlueprintBuilder — Specification 045"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import List, Optional

from .report_data import (
    ProductionReadinessReport, AxisScore, CriticalBlocker, Certificate,
    CacheInfo, CertificationProvenance,
    CONFIDENCE_HIGH, CONFIDENCE_MEDIUM, CONFIDENCE_LOW,
    CONFIDENCE_HIGH_THRESHOLD, CONFIDENCE_MEDIUM_THRESHOLD,
    VERDICT_REJECTED, VERDICT_CERTIFIED,
)

_log = logging.getLogger("engine.production_readiness.blueprint_builder")


class BlueprintBuilder:
    def build(
        self,
        axes: List[AxisScore],
        blockers: List[CriticalBlocker],
        certificate: Certificate,
        sources_used: List[str],
        sources_missing: List[str],
        overall_score: float = 0.0,
        certified: bool = False,
        self_verification_passed: bool = False,
        cache_info: Optional[CacheInfo] = None,
        confidence: float = 0.0,
    ) -> ProductionReadinessReport:
        conf_level = (
            CONFIDENCE_HIGH if confidence >= CONFIDENCE_HIGH_THRESHOLD
            else CONFIDENCE_MEDIUM if confidence >= CONFIDENCE_MEDIUM_THRESHOLD
            else CONFIDENCE_LOW
        )
        verdict = VERDICT_CERTIFIED if certified else VERDICT_REJECTED
        report = ProductionReadinessReport(
            report_id=str(uuid.uuid4()),
            axes=axes,
            blockers=blockers,
            certificate=certificate,
            findings=[],
            overall_score=overall_score,
            certified=certified,
            token_gate_open=certificate.token_gate_open if certificate else False,
            self_verification_passed=self_verification_passed,
            readiness_status=verdict,
            verdict=verdict,
            cache_info=cache_info or CacheInfo(),
            provenance=CertificationProvenance(
                engine_name="production_readiness",
                engine_version="1.0.0",
                sources_used=list(sources_used),
                sources_missing=list(sources_missing),
                generated_at=datetime.now(timezone.utc).isoformat(),
                confidence=confidence,
                confidence_level=conf_level,
                self_verification_passed=self_verification_passed,
            ),
            is_empty=len(axes) == 0,
        )
        _log.info(
            "BlueprintBuilder produced %s (certified=%s overall=%.1f blockers=%d)",
            report.report_id[:8], certified, overall_score, len(blockers),
        )
        return report


__all__ = ["BlueprintBuilder"]
