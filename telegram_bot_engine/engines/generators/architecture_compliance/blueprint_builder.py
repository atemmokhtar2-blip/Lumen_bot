"""BlueprintBuilder — Specification 037"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import List, Optional

from .report_data import (
    ArchitectureComplianceReport, ComplianceUnit, ArchitectureViolation,
    RefactoringSuggestion, CacheInfo, ComplianceProvenance,
    SEVERITY_CRITICAL, STATUS_OPEN,
    CONFIDENCE_HIGH, CONFIDENCE_MEDIUM, CONFIDENCE_LOW,
    CONFIDENCE_HIGH_THRESHOLD, CONFIDENCE_MEDIUM_THRESHOLD, VERDICT_NOT_READY,
)

_log = logging.getLogger("engine.architecture_compliance.blueprint_builder")


class BlueprintBuilder:
    def build(
        self,
        units: List[ComplianceUnit],
        violations: List[ArchitectureViolation],
        refactorings: List[RefactoringSuggestion],
        sources_used: List[str],
        sources_missing: List[str],
        compliance_score: float = 0.0,
        solid_score: float = 0.0,
        self_review_passed: bool = False,
        cache_info: Optional[CacheInfo] = None,
        confidence: float = 0.0,
    ) -> ArchitectureComplianceReport:
        conf_level = (
            CONFIDENCE_HIGH if confidence >= CONFIDENCE_HIGH_THRESHOLD
            else CONFIDENCE_MEDIUM if confidence >= CONFIDENCE_MEDIUM_THRESHOLD
            else CONFIDENCE_LOW
        )
        critical = [v for v in violations if v.severity == SEVERITY_CRITICAL]
        open_v = [v for v in violations if v.status == STATUS_OPEN]
        report = ArchitectureComplianceReport(
            report_id=str(uuid.uuid4()),
            units=units,
            violations=violations,
            refactorings=refactorings,
            findings=[],
            unit_count=len(units),
            violation_count=len(violations),
            critical_violation_count=len(critical),
            open_violation_count=len(open_v),
            compliance_score=round(compliance_score, 1),
            solid_score=round(solid_score, 1),
            self_review_passed=self_review_passed,
            readiness_status=VERDICT_NOT_READY,
            verdict=VERDICT_NOT_READY,
            cache_info=cache_info or CacheInfo(),
            provenance=ComplianceProvenance(
                engine_name="architecture_compliance",
                engine_version="1.0.0",
                sources_used=list(sources_used),
                sources_missing=list(sources_missing),
                generated_at=datetime.now(timezone.utc).isoformat(),
                confidence=confidence,
                confidence_level=conf_level,
                self_review_passed=self_review_passed,
            ),
            is_empty=len(units) == 0 and len(violations) == 0,
        )
        _log.info(
            "BlueprintBuilder produced %s (units=%d violations=%d score=%.1f)",
            report.report_id[:8], len(units), len(violations), compliance_score,
        )
        return report


__all__ = ["BlueprintBuilder"]
