"""BlueprintBuilder — Specification 035"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import List, Optional

from .report_data import (
    SecurityReviewReport, SecuredUnit, SecurityVulnerability, RiskItem,
    CacheInfo, SecurityProvenance,
    SEVERITY_CRITICAL, STATUS_FIXED, STATUS_OPEN,
    CONFIDENCE_HIGH, CONFIDENCE_MEDIUM, CONFIDENCE_LOW,
    CONFIDENCE_HIGH_THRESHOLD, CONFIDENCE_MEDIUM_THRESHOLD, VERDICT_NOT_READY,
)

_log = logging.getLogger("engine.security_review.blueprint_builder")


class BlueprintBuilder:
    def build(
        self,
        units: List[SecuredUnit],
        vulnerabilities: List[SecurityVulnerability],
        risks: List[RiskItem],
        sources_used: List[str],
        sources_missing: List[str],
        self_review_passed: bool = False,
        cache_info: Optional[CacheInfo] = None,
        confidence: float = 0.0,
    ) -> SecurityReviewReport:
        conf_level = (
            CONFIDENCE_HIGH if confidence >= CONFIDENCE_HIGH_THRESHOLD
            else CONFIDENCE_MEDIUM if confidence >= CONFIDENCE_MEDIUM_THRESHOLD
            else CONFIDENCE_LOW
        )
        critical = [v for v in vulnerabilities if v.severity == SEVERITY_CRITICAL]
        fixed = [v for v in vulnerabilities if v.status == STATUS_FIXED]
        open_crit = [
            v for v in critical if v.status == STATUS_OPEN
        ]
        avg = (
            round(sum(u.quality_after for u in units) / len(units), 1)
            if units else 0.0
        )
        report = SecurityReviewReport(
            report_id=str(uuid.uuid4()),
            units=units,
            vulnerabilities=vulnerabilities,
            findings=[],
            risks=risks,
            unit_count=len(units),
            vuln_count=len(vulnerabilities),
            critical_count=len(critical),
            fixed_count=len(fixed),
            open_critical_count=len(open_crit),
            average_quality_after=avg,
            self_review_passed=self_review_passed,
            readiness_status=VERDICT_NOT_READY,
            verdict=VERDICT_NOT_READY,
            cache_info=cache_info or CacheInfo(),
            provenance=SecurityProvenance(
                engine_name="security_review",
                engine_version="1.0.0",
                sources_used=list(sources_used),
                sources_missing=list(sources_missing),
                generated_at=datetime.now(timezone.utc).isoformat(),
                confidence=confidence,
                confidence_level=conf_level,
                self_review_passed=self_review_passed,
            ),
            is_empty=len(units) == 0 and len(vulnerabilities) == 0,
        )
        _log.info(
            "BlueprintBuilder produced %s (%d units, %d vulns, open_crit=%d)",
            report.report_id[:8], len(units), len(vulnerabilities), len(open_crit),
        )
        return report


__all__ = ["BlueprintBuilder"]
