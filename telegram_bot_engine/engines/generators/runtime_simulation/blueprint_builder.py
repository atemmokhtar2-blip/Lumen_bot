"""BlueprintBuilder — Specification 040"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import List, Optional

from .report_data import (
    RuntimeSimulationReport, SimulationEvent, StressResult, FailureScenario,
    ResourceSample, RuntimeScore, CacheInfo, RuntimeProvenance,
    STATUS_FAILED,
    CONFIDENCE_HIGH, CONFIDENCE_MEDIUM, CONFIDENCE_LOW,
    CONFIDENCE_HIGH_THRESHOLD, CONFIDENCE_MEDIUM_THRESHOLD, VERDICT_NOT_READY,
)

_log = logging.getLogger("engine.runtime_simulation.blueprint_builder")


class BlueprintBuilder:
    def build(
        self,
        events: List[SimulationEvent],
        stress_results: List[StressResult],
        failures: List[FailureScenario],
        resources: ResourceSample,
        score: RuntimeScore,
        sources_used: List[str],
        sources_missing: List[str],
        startup_ok: bool = False,
        leak_detected: bool = False,
        self_verification_passed: bool = False,
        runs_completed: int = 0,
        cache_info: Optional[CacheInfo] = None,
        confidence: float = 0.0,
    ) -> RuntimeSimulationReport:
        conf_level = (
            CONFIDENCE_HIGH if confidence >= CONFIDENCE_HIGH_THRESHOLD
            else CONFIDENCE_MEDIUM if confidence >= CONFIDENCE_MEDIUM_THRESHOLD
            else CONFIDENCE_LOW
        )
        failed = sum(1 for e in events if e.status == STATUS_FAILED)
        crashes = sum(
            1 for e in events
            if e.event_type in ("crash", "exception") and e.status == STATUS_FAILED
        )
        report = RuntimeSimulationReport(
            report_id=str(uuid.uuid4()),
            events=events,
            stress_results=stress_results,
            failures=failures,
            resources=resources,
            score=score,
            findings=[],
            event_count=len(events),
            failed_event_count=failed,
            crash_count=crashes,
            leak_detected=leak_detected,
            startup_ok=startup_ok,
            self_verification_passed=self_verification_passed,
            readiness_status=VERDICT_NOT_READY,
            verdict=VERDICT_NOT_READY,
            cache_info=cache_info or CacheInfo(),
            provenance=RuntimeProvenance(
                engine_name="runtime_simulation",
                engine_version="1.0.0",
                sources_used=list(sources_used),
                sources_missing=list(sources_missing),
                generated_at=datetime.now(timezone.utc).isoformat(),
                confidence=confidence,
                confidence_level=conf_level,
                self_verification_passed=self_verification_passed,
                runs_completed=runs_completed,
            ),
            is_empty=len(events) == 0,
        )
        _log.info(
            "BlueprintBuilder produced %s (events=%d failed=%d score=%.1f)",
            report.report_id[:8], len(events), failed, score.overall,
        )
        return report


__all__ = ["BlueprintBuilder"]
