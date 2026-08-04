"""BlueprintBuilder — Specification 044"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import List, Optional

from .report_data import (
    E2EScenarioTestingReport, VirtualUser, ScenarioResult, LoadResult,
    RecoveryResult, UXScore, CacheInfo, E2EProvenance,
    STATUS_FAILED,
    CONFIDENCE_HIGH, CONFIDENCE_MEDIUM, CONFIDENCE_LOW,
    CONFIDENCE_HIGH_THRESHOLD, CONFIDENCE_MEDIUM_THRESHOLD, VERDICT_NOT_READY,
)

_log = logging.getLogger("engine.e2e_scenario_testing.blueprint_builder")


class BlueprintBuilder:
    def build(
        self,
        users: List[VirtualUser],
        scenarios: List[ScenarioResult],
        load_results: List[LoadResult],
        recoveries: List[RecoveryResult],
        ux: UXScore,
        sources_used: List[str],
        sources_missing: List[str],
        self_verification_passed: bool = False,
        runs_completed: int = 0,
        cache_info: Optional[CacheInfo] = None,
        confidence: float = 0.0,
    ) -> E2EScenarioTestingReport:
        conf_level = (
            CONFIDENCE_HIGH if confidence >= CONFIDENCE_HIGH_THRESHOLD
            else CONFIDENCE_MEDIUM if confidence >= CONFIDENCE_MEDIUM_THRESHOLD
            else CONFIDENCE_LOW
        )
        failed = sum(1 for s in scenarios if s.status == STATUS_FAILED)
        unexpected = sum(1 for s in scenarios if s.unexpected_behavior)
        total = len(scenarios) or 1
        success_rate = round(100.0 * (total - failed) / total, 1)
        report = E2EScenarioTestingReport(
            report_id=str(uuid.uuid4()),
            users=users,
            scenarios=scenarios,
            load_results=load_results,
            recoveries=recoveries,
            ux=ux,
            findings=[],
            scenario_count=len(scenarios),
            failed_count=failed,
            unexpected_count=unexpected,
            success_rate=success_rate,
            self_verification_passed=self_verification_passed,
            readiness_status=VERDICT_NOT_READY,
            verdict=VERDICT_NOT_READY,
            cache_info=cache_info or CacheInfo(),
            provenance=E2EProvenance(
                engine_name="e2e_scenario_testing",
                engine_version="1.0.0",
                sources_used=list(sources_used),
                sources_missing=list(sources_missing),
                generated_at=datetime.now(timezone.utc).isoformat(),
                confidence=confidence,
                confidence_level=conf_level,
                self_verification_passed=self_verification_passed,
                runs_completed=runs_completed,
            ),
            is_empty=len(scenarios) == 0,
        )
        _log.info(
            "BlueprintBuilder produced %s (scenarios=%d failed=%d rate=%.1f)",
            report.report_id[:8], len(scenarios), failed, success_rate,
        )
        return report


__all__ = ["BlueprintBuilder"]
