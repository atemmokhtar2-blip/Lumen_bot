"""BlueprintBuilder — Specification 039"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import List, Optional

from .report_data import (
    StaticAnalysisReport, AnalyzedUnit, StaticIssue, RepairSuggestion,
    DependencyEdge, RiskItem, CacheInfo, StaticProvenance,
    SEVERITY_CRITICAL, STATUS_OPEN,
    CONFIDENCE_HIGH, CONFIDENCE_MEDIUM, CONFIDENCE_LOW,
    CONFIDENCE_HIGH_THRESHOLD, CONFIDENCE_MEDIUM_THRESHOLD, VERDICT_NOT_READY,
)

_log = logging.getLogger("engine.static_analysis.blueprint_builder")


class BlueprintBuilder:
    def build(
        self,
        units: List[AnalyzedUnit],
        issues: List[StaticIssue],
        suggestions: List[RepairSuggestion],
        dependencies: List[DependencyEdge],
        risks: List[RiskItem],
        sources_used: List[str],
        sources_missing: List[str],
        self_verification_passed: bool = False,
        cache_info: Optional[CacheInfo] = None,
        confidence: float = 0.0,
    ) -> StaticAnalysisReport:
        conf_level = (
            CONFIDENCE_HIGH if confidence >= CONFIDENCE_HIGH_THRESHOLD
            else CONFIDENCE_MEDIUM if confidence >= CONFIDENCE_MEDIUM_THRESHOLD
            else CONFIDENCE_LOW
        )
        critical = [i for i in issues if i.severity == SEVERITY_CRITICAL]
        open_crit = [i for i in critical if i.status == STATUS_OPEN]
        report = StaticAnalysisReport(
            report_id=str(uuid.uuid4()),
            units=units,
            issues=issues,
            suggestions=suggestions,
            dependencies=dependencies,
            risks=risks,
            findings=[],
            unit_count=len(units),
            issue_count=len(issues),
            critical_count=len(critical),
            open_critical_count=len(open_crit),
            suggestion_count=len(suggestions),
            self_verification_passed=self_verification_passed,
            readiness_status=VERDICT_NOT_READY,
            verdict=VERDICT_NOT_READY,
            cache_info=cache_info or CacheInfo(),
            provenance=StaticProvenance(
                engine_name="static_analysis",
                engine_version="1.0.0",
                sources_used=list(sources_used),
                sources_missing=list(sources_missing),
                generated_at=datetime.now(timezone.utc).isoformat(),
                confidence=confidence,
                confidence_level=conf_level,
                self_verification_passed=self_verification_passed,
            ),
            is_empty=len(units) == 0 and len(issues) == 0,
        )
        _log.info(
            "BlueprintBuilder produced %s (units=%d issues=%d open_crit=%d)",
            report.report_id[:8], len(units), len(issues), len(open_crit),
        )
        return report


__all__ = ["BlueprintBuilder"]
