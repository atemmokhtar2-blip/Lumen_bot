"""BlueprintBuilder — Specification 050"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import List, Optional

from .report_data import (
    DependencyManagementReport, Dependency, Conflict, SecurityIssue,
    HealthScore, LockEntry, RegistryEntry, CacheInfo, DepProvenance,
    CONFIDENCE_HIGH, CONFIDENCE_MEDIUM, CONFIDENCE_LOW,
    CONFIDENCE_HIGH_THRESHOLD, CONFIDENCE_MEDIUM_THRESHOLD, VERDICT_NOT_READY,
)

_log = logging.getLogger("engine.dependency_management.blueprint_builder")


class BlueprintBuilder:
    def build(
        self,
        dependencies: List[Dependency],
        conflicts: List[Conflict],
        security_issues: List[SecurityIssue],
        unused: List[str],
        lockfile: List[LockEntry],
        registry: List[RegistryEntry],
        health: HealthScore,
        sources_used: List[str],
        sources_missing: List[str],
        self_verification_passed: bool = False,
        cache_info: Optional[CacheInfo] = None,
        confidence: float = 0.0,
    ) -> DependencyManagementReport:
        conf_level = (
            CONFIDENCE_HIGH if confidence >= CONFIDENCE_HIGH_THRESHOLD
            else CONFIDENCE_MEDIUM if confidence >= CONFIDENCE_MEDIUM_THRESHOLD
            else CONFIDENCE_LOW
        )
        report = DependencyManagementReport(
            report_id=str(uuid.uuid4()),
            dependencies=dependencies,
            conflicts=conflicts,
            security_issues=security_issues,
            unused=unused,
            lockfile=lockfile,
            registry=registry,
            health=health,
            findings=[],
            dependency_count=len(dependencies),
            conflict_count=len(conflicts),
            unsafe_count=len(security_issues),
            unused_count=len(unused),
            self_verification_passed=self_verification_passed,
            readiness_status=VERDICT_NOT_READY,
            verdict=VERDICT_NOT_READY,
            cache_info=cache_info or CacheInfo(),
            provenance=DepProvenance(
                engine_name="dependency_management",
                engine_version="1.0.0",
                sources_used=list(sources_used),
                sources_missing=list(sources_missing),
                generated_at=datetime.now(timezone.utc).isoformat(),
                confidence=confidence,
                confidence_level=conf_level,
                self_verification_passed=self_verification_passed,
            ),
            is_empty=len(dependencies) == 0,
        )
        _log.info(
            "BlueprintBuilder produced %s (deps=%d conflicts=%d unsafe=%d health=%.1f)",
            report.report_id[:8], len(dependencies), len(conflicts),
            len(security_issues), health.overall,
        )
        return report


__all__ = ["BlueprintBuilder"]
