"""BlueprintBuilder — Specification 030"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import List, Optional

from .report_data import (
    InitializedProjectReport, ProjectIdentity, ScaffoldEntry,
    ProjectManifest, ProjectRegistry, BuildLogEntry, BuildConflict,
    CacheInfo, BuildProvenance, ENTRY_FOLDER, ENTRY_FILE,
    CONFIDENCE_HIGH, CONFIDENCE_MEDIUM, CONFIDENCE_LOW,
    CONFIDENCE_HIGH_THRESHOLD, CONFIDENCE_MEDIUM_THRESHOLD, VERDICT_NOT_READY,
)

_log = logging.getLogger("engine.project_builder.blueprint_builder")


class BlueprintBuilder:
    def build(
        self,
        identity: ProjectIdentity,
        entries: List[ScaffoldEntry],
        manifest: ProjectManifest,
        registry: ProjectRegistry,
        logs: List[BuildLogEntry],
        conflicts: List[BuildConflict],
        sources_used: List[str],
        sources_missing: List[str],
        cache_info: Optional[CacheInfo] = None,
        confidence: float = 0.0,
    ) -> InitializedProjectReport:
        conf_level = (
            CONFIDENCE_HIGH if confidence >= CONFIDENCE_HIGH_THRESHOLD
            else CONFIDENCE_MEDIUM if confidence >= CONFIDENCE_MEDIUM_THRESHOLD
            else CONFIDENCE_LOW
        )
        folder_count = sum(1 for e in entries if e.entry_type == ENTRY_FOLDER)
        file_count = sum(1 for e in entries if e.entry_type == ENTRY_FILE)
        report = InitializedProjectReport(
            report_id=str(uuid.uuid4()),
            identity=identity,
            entries=entries,
            manifest=manifest,
            registry=registry,
            logs=logs,
            conflicts=conflicts,
            findings=[],
            folder_count=folder_count,
            file_count=file_count,
            readiness_status=VERDICT_NOT_READY,
            verdict=VERDICT_NOT_READY,
            cache_info=cache_info or CacheInfo(),
            provenance=BuildProvenance(
                engine_name="project_builder",
                engine_version="1.0.0",
                sources_used=list(sources_used),
                sources_missing=list(sources_missing),
                generated_at=datetime.now(timezone.utc).isoformat(),
                confidence=confidence,
                confidence_level=conf_level,
            ),
            is_empty=len(entries) == 0,
        )
        _log.info(
            "BlueprintBuilder produced %s (folders=%d files=%d)",
            report.report_id[:8], folder_count, file_count,
        )
        return report


__all__ = ["BlueprintBuilder"]
