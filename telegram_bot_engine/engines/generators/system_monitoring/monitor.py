"""
SystemMonitor — Specification 057 (CRITICAL)

Real-time monitoring: resources, engines, health, performance,
anomaly detection, alerts, history and trend analysis.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Dict, List, Optional, Set, Tuple

from .data_readers import GenericData
from .report_data import (
    MetricSample, EngineStatus, HealthSnapshot, PerformanceSnapshot,
    AnomalyRecord, AlertRecord, HistoryEntry, TrendReport,
    STATE_RUNNING, STATE_WAITING, STATE_STOPPED, STATE_FAILED, STATE_COMPLETED,
    ANOMALY_SLOW_ENGINE, ANOMALY_UNEXPECTED_DELAY, ANOMALY_RESOURCE_SPIKE,
    ANOMALY_EXECUTION_LOOP,
    ALERT_ENGINE_FAILURE, ALERT_HIGH_MEMORY, ALERT_HIGH_CPU,
    ALERT_SYNC_FAILURE, ALERT_WORKSPACE_FAILURE,
    SEVERITY_CRITICAL, SEVERITY_HIGH, SEVERITY_MEDIUM,
    TREND_IMPROVING, TREND_STABLE, TREND_DEGRADING,
)

_log = logging.getLogger("engine.system_monitoring.monitor")

# Thresholds
_CPU_WARN, _CPU_CRIT = 70.0, 90.0
_RAM_WARN, _RAM_CRIT = 75.0, 90.0
_DISK_WARN, _DISK_CRIT = 80.0, 95.0
_SLOW_MS = 5000.0
_DELAY_MS = 3000.0


class SystemMonitor:
    """Collect metrics, detect anomalies, issue alerts, track trends."""

    def __init__(self) -> None:
        # In-memory history for trend analysis across runs in same process
        self._history_store: List[HistoryEntry] = []
        self._prev_health: float = 1.0
        self._prev_avg_exec: float = 0.0
        self._prev_fail_rate: float = 0.0

    def monitor(
        self,
        resource_data: GenericData,
        sync_data: GenericData,
        orch_data: GenericData,
        eco_data: GenericData,
        ctx_data: GenericData,
        workspace_data: GenericData,
        request_data: GenericData,
    ) -> Tuple[
        List[MetricSample],
        List[EngineStatus],
        HealthSnapshot,
        PerformanceSnapshot,
        List[AnomalyRecord],
        List[AlertRecord],
        List[HistoryEntry],
        TrendReport,
        bool,  # monitoring_self_ok
    ]:
        engines = self._collect_engines(
            request_data, orch_data, eco_data, resource_data,
        )
        statuses = self._engine_statuses(engines, request_data, orch_data)
        metrics = self._collect_metrics(
            resource_data, workspace_data, sync_data, statuses,
        )
        health = self._health(statuses, metrics)
        performance = self._performance(statuses)
        anomalies = self._detect_anomalies(statuses, metrics, request_data)
        alerts = self._issue_alerts(
            statuses, metrics, anomalies, sync_data, workspace_data,
        )
        history = self._record_history(metrics, statuses, anomalies, alerts)
        trend = self._analyse_trend(health, performance, statuses)
        self_ok = self._self_verify(metrics, statuses, health)

        _log.info(
            "SystemMonitor: engines=%d anomalies=%d alerts=%d health=%.2f",
            len(statuses), len(anomalies), len(alerts), health.overall_score,
        )
        return (
            metrics, statuses, health, performance,
            anomalies, alerts, history, trend, self_ok,
        )

    def self_verify(
        self,
        metrics: List[MetricSample],
        statuses: List[EngineStatus],
        health: HealthSnapshot,
        monitoring_self_ok: bool,
    ) -> bool:
        if not metrics:
            return False
        if not statuses:
            return False
        if health.overall_score < 0.0 or health.overall_score > 1.0:
            return False
        return monitoring_self_ok

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _collect_engines(
        self,
        request_data: GenericData,
        orch_data: GenericData,
        eco_data: GenericData,
        resource_data: GenericData,
    ) -> List[Dict]:
        engines: List[Dict] = []
        seen: Set[str] = set()

        for src in (
            eco_data.items or [],
            orch_data.items or [],
            resource_data.items or [],
            request_data.items or [],
        ):
            for it in src:
                if isinstance(it, str):
                    eid, state, pri = it, STATE_WAITING, 100
                elif isinstance(it, dict):
                    eid = str(
                        it.get("engine_id") or it.get("id")
                        or it.get("name") or ""
                    )
                    state = str(it.get("state") or STATE_WAITING)
                    pri = int(it.get("priority") or 100)
                else:
                    continue
                if not eid or eid in seen or eid == "system_monitoring":
                    continue
                seen.add(eid)
                engines.append({
                    "engine_id": eid,
                    "state": state,
                    "priority": pri,
                    "raw": it if isinstance(it, dict) else {},
                })

        if not engines:
            defaults = [
                ("analyzer", 10),
                ("intent_parser", 20),
                ("resource_management", 142),
                ("synchronization", 141),
                ("execution_context", 140),
            ]
            for eid, pri in defaults:
                engines.append({
                    "engine_id": eid, "state": STATE_WAITING,
                    "priority": pri, "raw": {},
                })

        engines.sort(key=lambda e: (e["priority"], e["engine_id"]))
        return engines

    def _engine_statuses(
        self,
        engines: List[Dict],
        request_data: GenericData,
        orch_data: GenericData,
    ) -> List[EngineStatus]:
        raw_req = request_data.raw or {}
        force_fail = bool(raw_req.get("force_engine_failure"))
        force_slow = bool(raw_req.get("force_slow_engine"))

        statuses: List[EngineStatus] = []
        for i, e in enumerate(engines):
            eid = e["engine_id"]
            raw = e.get("raw") or {}
            state = str(raw.get("state") or e.get("state") or STATE_WAITING)
            if force_fail and i == 0:
                state = STATE_FAILED
            if state not in (
                STATE_RUNNING, STATE_WAITING, STATE_STOPPED,
                STATE_FAILED, STATE_COMPLETED,
            ):
                state = STATE_WAITING

            exec_ms = float(raw.get("execution_time_ms") or (800 + i * 120))
            resp_ms = float(raw.get("response_time_ms") or (exec_ms * 0.6))
            queue_ms = float(raw.get("queue_time_ms") or (50 + i * 10))
            if force_slow and i == 0:
                exec_ms = _SLOW_MS + 1500

            health = 1.0
            last_error = ""
            if state == STATE_FAILED:
                health = 0.1
                last_error = str(raw.get("last_error") or "engine failed")
            elif state == STATE_STOPPED:
                health = 0.4
            elif exec_ms > _SLOW_MS:
                health = 0.55
            elif state == STATE_COMPLETED:
                health = 0.95
            elif state == STATE_RUNNING:
                health = 0.85

            statuses.append(EngineStatus(
                engine_id=eid,
                state=state,
                execution_time_ms=round(exec_ms, 1),
                response_time_ms=round(resp_ms, 1),
                queue_time_ms=round(queue_ms, 1),
                health_score=round(health, 3),
                last_error=last_error,
            ))
        return statuses

    def _collect_metrics(
        self,
        resource_data: GenericData,
        workspace_data: GenericData,
        sync_data: GenericData,
        statuses: List[EngineStatus],
    ) -> List[MetricSample]:
        res = resource_data.raw or {}
        system = res.get("system") or {}
        if not isinstance(system, dict):
            system = {}

        cpu = float(
            system.get("total_cpu_percent")
            or res.get("total_cpu_percent")
            or min(95.0, 12.0 * max(1, len(statuses)))
        )
        ram_used = float(
            system.get("total_ram_mb")
            or res.get("total_ram_mb")
            or (180.0 * max(1, len(statuses)))
        )
        ram_total = float(system.get("available_ram_mb") or 0) + ram_used
        if ram_total <= 0:
            ram_total = 4096.0
        ram_pct = round(min(100.0, (ram_used / ram_total) * 100.0), 1)

        disk_pct = float(
            res.get("disk_percent")
            or (workspace_data.raw or {}).get("disk_percent")
            or 35.0
        )
        threads = int(
            system.get("total_threads")
            or res.get("total_threads")
            or max(1, len(statuses) * 2)
        )
        network_mbps = float(
            (sync_data.raw or {}).get("network_mbps")
            or res.get("network_mbps")
            or 12.5
        )
        workspace_ok = 1.0 if workspace_data.available else 0.5
        engines_ok = sum(
            1 for s in statuses if s.state not in (STATE_FAILED, STATE_STOPPED)
        )

        def _status(val: float, warn: float, crit: float) -> str:
            if val >= crit:
                return "critical"
            if val >= warn:
                return "warn"
            return "ok"

        return [
            MetricSample(
                name="cpu", value=round(cpu, 1), unit="%",
                threshold_warn=_CPU_WARN, threshold_crit=_CPU_CRIT,
                status=_status(cpu, _CPU_WARN, _CPU_CRIT),
            ),
            MetricSample(
                name="ram", value=ram_pct, unit="%",
                threshold_warn=_RAM_WARN, threshold_crit=_RAM_CRIT,
                status=_status(ram_pct, _RAM_WARN, _RAM_CRIT),
            ),
            MetricSample(
                name="disk", value=round(disk_pct, 1), unit="%",
                threshold_warn=_DISK_WARN, threshold_crit=_DISK_CRIT,
                status=_status(disk_pct, _DISK_WARN, _DISK_CRIT),
            ),
            MetricSample(
                name="threads", value=float(threads), unit="count",
                threshold_warn=48, threshold_crit=60,
                status=_status(float(threads), 48, 60),
            ),
            MetricSample(
                name="network", value=network_mbps, unit="Mbps",
                threshold_warn=80, threshold_crit=95,
                status="ok",
            ),
            MetricSample(
                name="workspace", value=workspace_ok, unit="ratio",
                threshold_warn=0.5, threshold_crit=0.2,
                status="ok" if workspace_ok >= 0.5 else "warn",
            ),
            MetricSample(
                name="engines", value=float(engines_ok), unit="count",
                threshold_warn=0, threshold_crit=0,
                status="ok" if engines_ok > 0 else "critical",
            ),
        ]

    def _health(
        self,
        statuses: List[EngineStatus],
        metrics: List[MetricSample],
    ) -> HealthSnapshot:
        n = max(1, len(statuses))
        healthy = sum(1 for s in statuses if s.health_score >= 0.7)
        unhealthy = n - healthy
        failed = sum(1 for s in statuses if s.state == STATE_FAILED)
        availability = round((n - failed) / n, 3)
        reliability = round(sum(s.health_score for s in statuses) / n, 3)

        metric_penalty = 0.0
        for m in metrics:
            if m.status == "critical":
                metric_penalty += 0.15
            elif m.status == "warn":
                metric_penalty += 0.05

        overall = max(0.0, min(1.0, reliability - metric_penalty))
        return HealthSnapshot(
            overall_score=round(overall, 3),
            availability=availability,
            reliability=reliability,
            healthy_engines=healthy,
            unhealthy_engines=unhealthy,
        )

    def _performance(self, statuses: List[EngineStatus]) -> PerformanceSnapshot:
        if not statuses:
            return PerformanceSnapshot()
        execs = [s.execution_time_ms for s in statuses]
        resps = [s.response_time_ms for s in statuses]
        queues = [s.queue_time_ms for s in statuses]
        slow = sum(1 for e in execs if e >= _SLOW_MS)
        n = len(statuses)
        return PerformanceSnapshot(
            avg_execution_time_ms=round(sum(execs) / n, 1),
            avg_response_time_ms=round(sum(resps) / n, 1),
            avg_queue_time_ms=round(sum(queues) / n, 1),
            max_execution_time_ms=round(max(execs), 1),
            slow_engine_count=slow,
        )

    def _detect_anomalies(
        self,
        statuses: List[EngineStatus],
        metrics: List[MetricSample],
        request_data: GenericData,
    ) -> List[AnomalyRecord]:
        anomalies: List[AnomalyRecord] = []
        raw = request_data.raw or {}

        for s in statuses:
            if s.execution_time_ms >= _SLOW_MS:
                anomalies.append(AnomalyRecord(
                    anomaly_id=str(uuid.uuid4())[:8],
                    kind=ANOMALY_SLOW_ENGINE,
                    engine_id=s.engine_id,
                    severity=SEVERITY_HIGH,
                    message=f"Engine {s.engine_id} slow: {s.execution_time_ms}ms",
                    metric_value=s.execution_time_ms,
                ))
            if s.queue_time_ms >= _DELAY_MS:
                anomalies.append(AnomalyRecord(
                    anomaly_id=str(uuid.uuid4())[:8],
                    kind=ANOMALY_UNEXPECTED_DELAY,
                    engine_id=s.engine_id,
                    severity=SEVERITY_MEDIUM,
                    message=f"Unexpected queue delay on {s.engine_id}",
                    metric_value=s.queue_time_ms,
                ))
            if s.state == STATE_RUNNING and s.execution_time_ms > _SLOW_MS * 2:
                anomalies.append(AnomalyRecord(
                    anomaly_id=str(uuid.uuid4())[:8],
                    kind=ANOMALY_EXECUTION_LOOP,
                    engine_id=s.engine_id,
                    severity=SEVERITY_CRITICAL,
                    message=f"Possible execution loop on {s.engine_id}",
                    metric_value=s.execution_time_ms,
                ))

        for m in metrics:
            if m.name in ("cpu", "ram") and m.status == "critical":
                anomalies.append(AnomalyRecord(
                    anomaly_id=str(uuid.uuid4())[:8],
                    kind=ANOMALY_RESOURCE_SPIKE,
                    engine_id="system",
                    severity=SEVERITY_CRITICAL,
                    message=f"Resource spike: {m.name}={m.value}{m.unit}",
                    metric_value=m.value,
                ))

        if raw.get("force_loop"):
            anomalies.append(AnomalyRecord(
                anomaly_id=str(uuid.uuid4())[:8],
                kind=ANOMALY_EXECUTION_LOOP,
                engine_id="forced",
                severity=SEVERITY_CRITICAL,
                message="Forced execution loop anomaly for testing",
                metric_value=0.0,
            ))

        return anomalies

    def _issue_alerts(
        self,
        statuses: List[EngineStatus],
        metrics: List[MetricSample],
        anomalies: List[AnomalyRecord],
        sync_data: GenericData,
        workspace_data: GenericData,
    ) -> List[AlertRecord]:
        alerts: List[AlertRecord] = []

        for s in statuses:
            if s.state == STATE_FAILED:
                alerts.append(AlertRecord(
                    alert_id=str(uuid.uuid4())[:8],
                    kind=ALERT_ENGINE_FAILURE,
                    severity=SEVERITY_CRITICAL,
                    message=f"Engine failure: {s.engine_id} — {s.last_error or 'unknown'}",
                    source=s.engine_id,
                ))

        for m in metrics:
            if m.name == "cpu" and m.status in ("warn", "critical"):
                alerts.append(AlertRecord(
                    alert_id=str(uuid.uuid4())[:8],
                    kind=ALERT_HIGH_CPU,
                    severity=SEVERITY_CRITICAL if m.status == "critical" else SEVERITY_HIGH,
                    message=f"High CPU: {m.value}%",
                    source="system",
                ))
            if m.name == "ram" and m.status in ("warn", "critical"):
                alerts.append(AlertRecord(
                    alert_id=str(uuid.uuid4())[:8],
                    kind=ALERT_HIGH_MEMORY,
                    severity=SEVERITY_CRITICAL if m.status == "critical" else SEVERITY_HIGH,
                    message=f"High memory: {m.value}%",
                    source="system",
                ))

        if sync_data.available is False and sync_data.error:
            alerts.append(AlertRecord(
                alert_id=str(uuid.uuid4())[:8],
                kind=ALERT_SYNC_FAILURE,
                severity=SEVERITY_HIGH,
                message=f"Synchronization issue: {sync_data.error}",
                source="synchronization",
            ))
        elif (sync_data.raw or {}).get("failed") or (sync_data.raw or {}).get("sync_failed"):
            alerts.append(AlertRecord(
                alert_id=str(uuid.uuid4())[:8],
                kind=ALERT_SYNC_FAILURE,
                severity=SEVERITY_CRITICAL,
                message="Synchronization failure reported",
                source="synchronization",
            ))

        if workspace_data.available is False and workspace_data.error:
            alerts.append(AlertRecord(
                alert_id=str(uuid.uuid4())[:8],
                kind=ALERT_WORKSPACE_FAILURE,
                severity=SEVERITY_HIGH,
                message=f"Workspace issue: {workspace_data.error}",
                source="workspace",
            ))
        elif (workspace_data.raw or {}).get("failed"):
            alerts.append(AlertRecord(
                alert_id=str(uuid.uuid4())[:8],
                kind=ALERT_WORKSPACE_FAILURE,
                severity=SEVERITY_CRITICAL,
                message="Workspace failure reported",
                source="workspace",
            ))

        # Anomalies of critical severity also raise alerts
        for a in anomalies:
            if a.severity == SEVERITY_CRITICAL and a.kind == ANOMALY_EXECUTION_LOOP:
                alerts.append(AlertRecord(
                    alert_id=str(uuid.uuid4())[:8],
                    kind=ALERT_ENGINE_FAILURE,
                    severity=SEVERITY_CRITICAL,
                    message=a.message,
                    source=a.engine_id or "system",
                ))

        return alerts

    def _record_history(
        self,
        metrics: List[MetricSample],
        statuses: List[EngineStatus],
        anomalies: List[AnomalyRecord],
        alerts: List[AlertRecord],
    ) -> List[HistoryEntry]:
        now = datetime.now(timezone.utc).isoformat()
        entries: List[HistoryEntry] = []

        cpu = next((m.value for m in metrics if m.name == "cpu"), 0.0)
        entries.append(HistoryEntry(
            timestamp=now,
            event_type="performance",
            summary=f"CPU={cpu}% engines={len(statuses)}",
            details={"cpu": cpu, "engine_count": len(statuses)},
        ))

        for a in alerts:
            entries.append(HistoryEntry(
                timestamp=now,
                event_type="alert",
                summary=a.message,
                details=a.to_dict(),
            ))

        for s in statuses:
            if s.state == STATE_FAILED:
                entries.append(HistoryEntry(
                    timestamp=now,
                    event_type="failure",
                    summary=f"Engine {s.engine_id} failed",
                    details=s.to_dict(),
                ))

        for an in anomalies:
            entries.append(HistoryEntry(
                timestamp=now,
                event_type="state_change",
                summary=an.message,
                details=an.to_dict(),
            ))

        self._history_store.extend(entries)
        # Keep last 200 entries
        if len(self._history_store) > 200:
            self._history_store = self._history_store[-200:]
        return list(entries)

    def _analyse_trend(
        self,
        health: HealthSnapshot,
        performance: PerformanceSnapshot,
        statuses: List[EngineStatus],
    ) -> TrendReport:
        n = max(1, len(statuses))
        fail_rate = sum(1 for s in statuses if s.state == STATE_FAILED) / n
        health_delta = round(health.overall_score - self._prev_health, 3)
        perf_delta = round(
            self._prev_avg_exec - performance.avg_execution_time_ms, 1,
        )  # positive = faster
        fail_delta = round(fail_rate - self._prev_fail_rate, 3)

        # Update baselines for next run
        self._prev_health = health.overall_score
        self._prev_avg_exec = performance.avg_execution_time_ms
        self._prev_fail_rate = fail_rate

        score = 0
        if health_delta > 0.02:
            score += 1
        elif health_delta < -0.02:
            score -= 1
        if perf_delta > 50:
            score += 1
        elif perf_delta < -50:
            score -= 1
        if fail_delta < -0.01:
            score += 1
        elif fail_delta > 0.01:
            score -= 1

        if score >= 1:
            direction = TREND_IMPROVING
            notes = "Health/performance trending upward."
        elif score <= -1:
            direction = TREND_DEGRADING
            notes = "Health/performance trending downward."
        else:
            direction = TREND_STABLE
            notes = "No significant change detected."

        return TrendReport(
            direction=direction,
            performance_delta=perf_delta,
            failure_rate_delta=fail_delta,
            health_delta=health_delta,
            notes=notes,
        )

    def _self_verify(
        self,
        metrics: List[MetricSample],
        statuses: List[EngineStatus],
        health: HealthSnapshot,
    ) -> bool:
        """Verify that monitoring itself is producing coherent data."""
        if not metrics:
            return False
        names = {m.name for m in metrics}
        required = {"cpu", "ram", "disk", "threads", "engines"}
        if not required.issubset(names):
            return False
        if not statuses:
            return False
        if health.overall_score < 0.0 or health.overall_score > 1.0:
            return False
        return True


__all__ = ["SystemMonitor"]
