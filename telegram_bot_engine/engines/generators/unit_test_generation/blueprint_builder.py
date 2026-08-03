"""BlueprintBuilder — Specification 043"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import List, Optional

from .report_data import (
    UnitTestGenerationReport, GeneratedTest, CoverageGap, FailureRecord,
    CoverageScore, CacheInfo, UnitTestProvenance,
    CONFIDENCE_HIGH, CONFIDENCE_MEDIUM, CONFIDENCE_LOW,
    CONFIDENCE_HIGH_THRESHOLD, CONFIDENCE_MEDIUM_THRESHOLD, VERDICT_NOT_READY,
)

_log = logging.getLogger("engine.unit_test_generation.blueprint_builder")


class BlueprintBuilder:
    def build(
        self,
        tests: List[GeneratedTest],
        gaps: List[CoverageGap],
        failures: List[FailureRecord],
        coverage: CoverageScore,
        sources_used: List[str],
        sources_missing: List[str],
        all_tests_passed: bool = False,
        self_verification_passed: bool = False,
        cache_info: Optional[CacheInfo] = None,
        confidence: float = 0.0,
    ) -> UnitTestGenerationReport:
        conf_level = (
            CONFIDENCE_HIGH if confidence >= CONFIDENCE_HIGH_THRESHOLD
            else CONFIDENCE_MEDIUM if confidence >= CONFIDENCE_MEDIUM_THRESHOLD
            else CONFIDENCE_LOW
        )
        case_count = sum(len(t.cases) for t in tests)
        report = UnitTestGenerationReport(
            report_id=str(uuid.uuid4()),
            tests=tests,
            gaps=gaps,
            failures=failures,
            coverage=coverage,
            findings=[],
            test_count=len(tests),
            case_count=case_count,
            gap_count=len(gaps),
            failure_count=len(failures),
            all_tests_passed=all_tests_passed,
            self_verification_passed=self_verification_passed,
            readiness_status=VERDICT_NOT_READY,
            verdict=VERDICT_NOT_READY,
            cache_info=cache_info or CacheInfo(),
            provenance=UnitTestProvenance(
                engine_name="unit_test_generation",
                engine_version="1.0.0",
                sources_used=list(sources_used),
                sources_missing=list(sources_missing),
                generated_at=datetime.now(timezone.utc).isoformat(),
                confidence=confidence,
                confidence_level=conf_level,
                self_verification_passed=self_verification_passed,
            ),
            is_empty=len(tests) == 0,
        )
        _log.info(
            "BlueprintBuilder produced %s (tests=%d cases=%d gaps=%d cov=%.1f)",
            report.report_id[:8], len(tests), case_count, len(gaps), coverage.overall,
        )
        return report


__all__ = ["BlueprintBuilder"]
