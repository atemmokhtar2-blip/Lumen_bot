"""BlueprintBuilder — Specification 059"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import List, Optional

from .report_data import (
    ConfigurationManagementReport, ConfigEntry, ValidationIssue,
    ConfigVersion, BackupRecord, RecoveryRecord, ConfigChangeLog,
    CacheInfo, ConfigProvenance,
    CONFIDENCE_HIGH, CONFIDENCE_MEDIUM, CONFIDENCE_LOW,
    CONFIDENCE_HIGH_THRESHOLD, CONFIDENCE_MEDIUM_THRESHOLD, VERDICT_NOT_READY,
)

_log = logging.getLogger("engine.configuration_management.blueprint_builder")


class BlueprintBuilder:
    def build(
        self,
        entries: List[ConfigEntry],
        issues: List[ValidationIssue],
        versions: List[ConfigVersion],
        backups: List[BackupRecord],
        recoveries: List[RecoveryRecord],
        change_log: List[ConfigChangeLog],
        sources_used: List[str],
        sources_missing: List[str],
        current_version: int = 0,
        synced: bool = False,
        external_config_violations: int = 0,
        protected_keys: int = 0,
        self_verification_passed: bool = False,
        cache_info: Optional[CacheInfo] = None,
        confidence: float = 0.0,
    ) -> ConfigurationManagementReport:
        conf_level = (
            CONFIDENCE_HIGH if confidence >= CONFIDENCE_HIGH_THRESHOLD
            else CONFIDENCE_MEDIUM if confidence >= CONFIDENCE_MEDIUM_THRESHOLD
            else CONFIDENCE_LOW
        )
        report = ConfigurationManagementReport(
            report_id=str(uuid.uuid4()),
            entries=entries,
            issues=issues,
            versions=versions,
            backups=backups,
            recoveries=recoveries,
            change_log=change_log,
            findings=[],
            entry_count=len(entries),
            issue_count=len(issues),
            current_version=current_version,
            synced=synced,
            external_config_violations=external_config_violations,
            protected_keys=protected_keys,
            self_verification_passed=self_verification_passed,
            readiness_status=VERDICT_NOT_READY,
            verdict=VERDICT_NOT_READY,
            cache_info=cache_info or CacheInfo(),
            provenance=ConfigProvenance(
                engine_name="configuration_management",
                engine_version="1.0.0",
                sources_used=list(sources_used),
                sources_missing=list(sources_missing),
                generated_at=datetime.now(timezone.utc).isoformat(),
                confidence=confidence,
                confidence_level=conf_level,
                self_verification_passed=self_verification_passed,
            ),
            is_empty=len(entries) == 0,
        )
        _log.info(
            "BlueprintBuilder produced %s (entries=%d issues=%d v=%d)",
            report.report_id[:8], len(entries), len(issues), current_version,
        )
        return report


__all__ = ["BlueprintBuilder"]
