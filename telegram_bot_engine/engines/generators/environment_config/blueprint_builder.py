"""BlueprintBuilder — Specification 051"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import List, Optional

from .report_data import (
    EnvironmentConfigReport, EnvironmentProfile, EnvVariable, HealthCheck,
    ConfigBackup, EnvScore, CacheInfo, EnvProvenance,
    ENV_DEVELOPMENT,
    CONFIDENCE_HIGH, CONFIDENCE_MEDIUM, CONFIDENCE_LOW,
    CONFIDENCE_HIGH_THRESHOLD, CONFIDENCE_MEDIUM_THRESHOLD, VERDICT_NOT_READY,
)

_log = logging.getLogger("engine.environment_config.blueprint_builder")


class BlueprintBuilder:
    def build(
        self,
        profiles: List[EnvironmentProfile],
        variables: List[EnvVariable],
        health_checks: List[HealthCheck],
        backups: List[ConfigBackup],
        score: EnvScore,
        sources_used: List[str],
        sources_missing: List[str],
        detected_environment: str = ENV_DEVELOPMENT,
        secrets_isolated: bool = True,
        self_verification_passed: bool = False,
        cache_info: Optional[CacheInfo] = None,
        confidence: float = 0.0,
    ) -> EnvironmentConfigReport:
        conf_level = (
            CONFIDENCE_HIGH if confidence >= CONFIDENCE_HIGH_THRESHOLD
            else CONFIDENCE_MEDIUM if confidence >= CONFIDENCE_MEDIUM_THRESHOLD
            else CONFIDENCE_LOW
        )
        missing = sum(1 for v in variables if v.required and not v.value_present)
        unsafe = sum(1 for v in variables if not v.safe)
        report = EnvironmentConfigReport(
            report_id=str(uuid.uuid4()),
            profiles=profiles,
            variables=variables,
            health_checks=health_checks,
            backups=backups,
            score=score,
            findings=[],
            detected_environment=detected_environment,
            secrets_isolated=secrets_isolated,
            missing_count=missing,
            unsafe_count=unsafe,
            self_verification_passed=self_verification_passed,
            readiness_status=VERDICT_NOT_READY,
            verdict=VERDICT_NOT_READY,
            cache_info=cache_info or CacheInfo(),
            provenance=EnvProvenance(
                engine_name="environment_config",
                engine_version="1.0.0",
                sources_used=list(sources_used),
                sources_missing=list(sources_missing),
                generated_at=datetime.now(timezone.utc).isoformat(),
                confidence=confidence,
                confidence_level=conf_level,
                self_verification_passed=self_verification_passed,
            ),
            is_empty=len(profiles) == 0 and len(variables) == 0,
        )
        _log.info(
            "BlueprintBuilder produced %s (profiles=%d vars=%d missing=%d score=%.1f)",
            report.report_id[:8], len(profiles), len(variables), missing, score.overall,
        )
        return report


__all__ = ["BlueprintBuilder"]
