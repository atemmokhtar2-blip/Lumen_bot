"""BlueprintBuilder — Specification 057"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import List, Optional

from .report_data import (
    SystemMonitoringReport, MetricSample, EngineStatus, HealthSnapshot,
    PerformanceSnapshot, AnomalyRecord, AlertRecord, HistoryEntry, TrendReport,
    CacheInfo, MonitoringProvenance,
    CONFIDENCE_HIGH, CONFIDENCE_MEDIUM, CONFIDENCE_LOW,
    CONFIDENCE_HIGH_THRESHOLD, CONFIDENCE_MEDIUM_THRESHOLD, VERDICT_NOT_READY,
    SEVERITY_CRITICAL,
)

_log = logging.getLogger("engine.system_monitoring.blueprint_builder")


class BlueprintBuilder:
    def build(
        self,
        metrics: List[MetricSample],
        engine_statuses: List[EngineStatus],
        health: HealthSnapshot,
        performance: PerformanceSnapshot,
        anomalies: List[AnomalyRecord],
        alerts: List[AlertRecord],
        history: List[HistoryEntry],
        trend: TrendReport,
        sources_used: List[str],
        sources_missing: List[str],
        self_verification_passed: bool = False,
        monitoring_self_ok: bool = False,
        cache_info: Optional[CacheInfo] = None,
        confidence: float = 0.0,
    ) -> SystemMonitoringReport:
        conf_level = (
            CONFIDENCE_HIGH if confidence >= CONFIDENCE_HIGH_THRESHOLD
            else CONFIDENCE_MEDIUM if confidence >= CONFIDENCE_MEDIUM_THRESHOLD
            else CONFIDENCE_LOW
        )
        critical_alerts = sum(
            1 for a in alerts if a.severity == SEVERITY_CRITICAL
        )
        report = SystemMonitoringReport(
            report_id=str(uuid.uuid4()),
            metrics=metrics,
            engine_statuses=engine_statuses,
            health=health,
            performance=performance,
            anomalies=anomalies,
            alerts=alerts,
            history=history,
            trend=trend,
            findings=[],
            engine_count=len(engine_statuses),
            anomaly_count=len(anomalies),
            alert_count=len(alerts),
            critical_alert_count=critical_alerts,
            self_verification_passed=self_verification_passed,
            monitoring_self_ok=monitoring_self_ok,
            readiness_status=VERDICT_NOT_READY,
            verdict=VERDICT_NOT_READY,
            cache_info=cache_info or CacheInfo(),
            provenance=MonitoringProvenance(
                engine_name="system_monitoring",
                engine_version="1.0.0",
                sources_used=list(sources_used),
                sources_missing=list(sources_missing),
                generated_at=datetime.now(timezone.utc).isoformat(),
                confidence=confidence,
                confidence_level=conf_level,
                self_verification_passed=self_verification_passed,
            ),
            is_empty=len(engine_statuses) == 0 and len(metrics) == 0,
        )
        _log.info(
            "BlueprintBuilder produced %s (engines=%d anomalies=%d alerts=%d)",
            report.report_id[:8], len(engine_statuses), len(anomalies), len(alerts),
        )
        return report


__all__ = ["BlueprintBuilder"]
