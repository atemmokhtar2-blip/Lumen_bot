"""BlueprintBuilder — Specification 038"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import List, Optional

from .report_data import (
    CodeRefactoringReport, RefactoredUnit, CodeSmell, RefactoringAction,
    ExtensibilityPoint, MaintainabilityScore, CacheInfo, RefactoringProvenance,
    STATUS_REJECTED,
    CONFIDENCE_HIGH, CONFIDENCE_MEDIUM, CONFIDENCE_LOW,
    CONFIDENCE_HIGH_THRESHOLD, CONFIDENCE_MEDIUM_THRESHOLD, VERDICT_NOT_READY,
)

_log = logging.getLogger("engine.code_refactoring.blueprint_builder")


class BlueprintBuilder:
    def build(
        self,
        units: List[RefactoredUnit],
        smells: List[CodeSmell],
        actions: List[RefactoringAction],
        extensibility_points: List[ExtensibilityPoint],
        maintainability: MaintainabilityScore,
        sources_used: List[str],
        sources_missing: List[str],
        self_verification_passed: bool = False,
        regression_safe: bool = True,
        cache_info: Optional[CacheInfo] = None,
        confidence: float = 0.0,
    ) -> CodeRefactoringReport:
        conf_level = (
            CONFIDENCE_HIGH if confidence >= CONFIDENCE_HIGH_THRESHOLD
            else CONFIDENCE_MEDIUM if confidence >= CONFIDENCE_MEDIUM_THRESHOLD
            else CONFIDENCE_LOW
        )
        rejected = sum(1 for a in actions if a.status == STATUS_REJECTED)
        avg = (
            round(sum(u.maintainability_after for u in units) / len(units), 1)
            if units else 0.0
        )
        report = CodeRefactoringReport(
            report_id=str(uuid.uuid4()),
            units=units,
            smells=smells,
            actions=actions,
            findings=[],
            extensibility_points=extensibility_points,
            maintainability=maintainability,
            unit_count=len(units),
            smell_count=len(smells),
            action_count=len(actions),
            rejected_count=rejected,
            average_maintainability_after=avg,
            self_verification_passed=self_verification_passed,
            regression_safe=regression_safe,
            readiness_status=VERDICT_NOT_READY,
            verdict=VERDICT_NOT_READY,
            cache_info=cache_info or CacheInfo(),
            provenance=RefactoringProvenance(
                engine_name="code_refactoring",
                engine_version="1.0.0",
                sources_used=list(sources_used),
                sources_missing=list(sources_missing),
                generated_at=datetime.now(timezone.utc).isoformat(),
                confidence=confidence,
                confidence_level=conf_level,
                self_verification_passed=self_verification_passed,
                regression_safe=regression_safe,
            ),
            is_empty=len(units) == 0 and len(smells) == 0,
        )
        _log.info(
            "BlueprintBuilder produced %s (units=%d smells=%d actions=%d)",
            report.report_id[:8], len(units), len(smells), len(actions),
        )
        return report


__all__ = ["BlueprintBuilder"]
