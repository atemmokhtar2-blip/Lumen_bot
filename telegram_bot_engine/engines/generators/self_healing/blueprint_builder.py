"""BlueprintBuilder — Specification 041"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import List, Optional

from .report_data import (
    SelfHealingReport, IssueRecord, RepairPlan, RepairAttempt,
    ValidationCycleResult, CacheInfo, HealingProvenance,
    STATUS_HEALED, STATUS_FAILED, STATUS_SKIPPED,
    CONFIDENCE_HIGH, CONFIDENCE_MEDIUM, CONFIDENCE_LOW,
    CONFIDENCE_HIGH_THRESHOLD, CONFIDENCE_MEDIUM_THRESHOLD, VERDICT_NOT_READY,
)

_log = logging.getLogger("engine.self_healing.blueprint_builder")


class BlueprintBuilder:
    def build(
        self,
        issues: List[IssueRecord],
        plans: List[RepairPlan],
        attempts: List[RepairAttempt],
        validation_cycles: List[ValidationCycleResult],
        sources_used: List[str],
        sources_missing: List[str],
        all_validations_passed: bool = False,
        self_verification_passed: bool = False,
        cache_info: Optional[CacheInfo] = None,
        confidence: float = 0.0,
    ) -> SelfHealingReport:
        conf_level = (
            CONFIDENCE_HIGH if confidence >= CONFIDENCE_HIGH_THRESHOLD
            else CONFIDENCE_MEDIUM if confidence >= CONFIDENCE_MEDIUM_THRESHOLD
            else CONFIDENCE_LOW
        )
        healed = sum(1 for i in issues if i.status == STATUS_HEALED)
        failed = sum(1 for i in issues if i.status == STATUS_FAILED)
        skipped = sum(1 for i in issues if i.status == STATUS_SKIPPED)
        avg_conf = (
            round(sum(p.confidence for p in plans) / len(plans), 3)
            if plans else 0.0
        )
        report = SelfHealingReport(
            report_id=str(uuid.uuid4()),
            issues=issues,
            plans=plans,
            attempts=attempts,
            validation_cycles=validation_cycles,
            findings=[],
            issue_count=len(issues),
            healed_count=healed,
            failed_count=failed,
            skipped_count=skipped,
            average_confidence=avg_conf,
            all_validations_passed=all_validations_passed,
            self_verification_passed=self_verification_passed,
            readiness_status=VERDICT_NOT_READY,
            verdict=VERDICT_NOT_READY,
            cache_info=cache_info or CacheInfo(),
            provenance=HealingProvenance(
                engine_name="self_healing",
                engine_version="1.0.0",
                sources_used=list(sources_used),
                sources_missing=list(sources_missing),
                generated_at=datetime.now(timezone.utc).isoformat(),
                confidence=confidence,
                confidence_level=conf_level,
                self_verification_passed=self_verification_passed,
            ),
            is_empty=len(issues) == 0,
        )
        _log.info(
            "BlueprintBuilder produced %s (issues=%d healed=%d failed=%d)",
            report.report_id[:8], len(issues), healed, failed,
        )
        return report


__all__ = ["BlueprintBuilder"]
