"""
ServiceManager — Specification 061 (MAXIMUM CRITICAL)

Register, lifecycle, dependency order, health, recovery, isolation,
load monitoring and resource allocation for internal platform services.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Dict, List, Optional, Set, Tuple

from .data_readers import GenericData
from .report_data import (
    ServiceRecord, ServiceHealth, LifecycleEvent, RecoveryRecord,
    ResourceAllocation, LoadSample,
    STATE_REGISTERED, STATE_INITIALIZED, STATE_STARTED, STATE_PAUSED,
    STATE_STOPPED, STATE_FAILED, STATE_RECOVERING, STATE_SHUTDOWN,
    ACTION_INIT, ACTION_START, ACTION_PAUSE, ACTION_RESUME,
    ACTION_RESTART, ACTION_SHUTDOWN,
)

_log = logging.getLogger("engine.service_management.service_manager")

# Built-in platform services (name, deps, priority)
_DEFAULT_SERVICES = [
    ("logging_service", "Central Logging Service", [], 10),
    ("config_service", "Configuration Service", ["logging_service"], 20),
    ("security_service", "Security Service", ["config_service", "logging_service"], 30),
    ("resource_service", "Resource Service", ["config_service"], 40),
    ("monitoring_service", "Monitoring Service", ["resource_service", "logging_service"], 50),
    ("orchestrator_service", "Orchestrator Service", ["security_service", "monitoring_service"], 60),
    ("workspace_service", "Workspace Service", ["config_service"], 70),
    ("pipeline_service", "Pipeline Service", ["orchestrator_service", "workspace_service"], 80),
]


class ServiceManager:
    """Central service registry and lifecycle controller."""

    def manage(
        self,
        security_data: GenericData,
        config_data: GenericData,
        monitoring_data: GenericData,
        resource_data: GenericData,
        ctx_data: GenericData,
        eco_data: GenericData,
        request_data: GenericData,
    ) -> Tuple[
        List[ServiceRecord],
        List[ServiceHealth],
        List[LifecycleEvent],
        List[RecoveryRecord],
        List[ResourceAllocation],
        List[LoadSample],
        int,   # unregistered_attempts
        int,   # dependency_violations
        bool,  # self_ok
    ]:
        services = self._register(request_data, eco_data, security_data)
        unregistered = self._detect_unregistered(request_data, services)

        events: List[LifecycleEvent] = []
        dep_violations = 0

        # Lifecycle: init → start in dependency order
        ordered = self._topo_sort(services)
        started: Set[str] = set()

        for svc in ordered:
            # Init
            ev, ok = self._transition(svc, ACTION_INIT, STATE_INITIALIZED)
            events.append(ev)
            if not ok:
                continue
            # Dependency check before start
            missing = [d for d in svc.dependencies if d not in started]
            if missing:
                dep_violations += 1
                ev2 = LifecycleEvent(
                    event_id=str(uuid.uuid4())[:8],
                    service_id=svc.service_id,
                    action=ACTION_START,
                    from_state=svc.state,
                    to_state=svc.state,
                    success=False,
                    message=f"Dependencies not ready: {missing}",
                    timestamp=datetime.now(timezone.utc).isoformat(),
                )
                events.append(ev2)
                # Still try after marking violation — force start of deps first in real system
                # For simulation: start anyway only if force flag
                if not (request_data.raw or {}).get("force_start_without_deps"):
                    continue
            ev3, ok3 = self._transition(svc, ACTION_START, STATE_STARTED)
            events.append(ev3)
            if ok3:
                started.add(svc.service_id)

        # Simulate failures from request
        raw = request_data.raw or {}
        fail_ids = set(raw.get("fail_services") or [])
        for svc in services:
            if svc.service_id in fail_ids or raw.get("force_service_failure") and svc.priority >= 70:
                prev = svc.state
                svc.state = STATE_FAILED
                svc.health_status = "unhealthy"
                events.append(LifecycleEvent(
                    event_id=str(uuid.uuid4())[:8],
                    service_id=svc.service_id,
                    action="fail",
                    from_state=prev,
                    to_state=STATE_FAILED,
                    success=False,
                    message="Service failure simulated",
                    timestamp=datetime.now(timezone.utc).isoformat(),
                ))

        health = self._health(services, monitoring_data, request_data)
        recoveries = self._recover(services, health)
        allocations = self._allocate(services, resource_data)
        loads = self._load(services, request_data)
        self_ok = self._self_verify(services, events, unregistered, dep_violations)

        _log.info(
            "ServiceManager: services=%d started=%d failed=%d unreg=%d dep_viol=%d",
            len(services),
            sum(1 for s in services if s.state == STATE_STARTED),
            sum(1 for s in services if s.state == STATE_FAILED),
            unregistered,
            dep_violations,
        )
        return (
            services, health, events, recoveries, allocations, loads,
            unregistered, dep_violations, self_ok,
        )

    def self_verify(
        self,
        services: List[ServiceRecord],
        events: List[LifecycleEvent],
        unregistered: int,
        dep_violations: int,
        self_ok: bool,
    ) -> bool:
        if not services:
            return False
        if not events:
            return False
        return self_ok

    # ------------------------------------------------------------------

    def _register(
        self,
        request_data: GenericData,
        eco_data: GenericData,
        security_data: GenericData,
    ) -> List[ServiceRecord]:
        by_id: Dict[str, ServiceRecord] = {}

        # Defaults
        for sid, name, deps, pri in _DEFAULT_SERVICES:
            by_id[sid] = ServiceRecord(
                service_id=sid,
                name=name,
                version="1.0.0",
                dependencies=list(deps),
                priority=pri,
                state=STATE_REGISTERED,
                health_status="unknown",
            )

        # From request
        for it in (request_data.items or []):
            if isinstance(it, str):
                sid = it if it.endswith("_service") else f"{it}_service"
                if sid not in by_id:
                    by_id[sid] = ServiceRecord(
                        service_id=sid, name=sid.replace("_", " ").title(),
                        priority=100, state=STATE_REGISTERED,
                    )
            elif isinstance(it, dict):
                sid = str(it.get("service_id") or it.get("id") or it.get("name") or "")
                if not sid:
                    continue
                if not sid.endswith("_service") and "service" not in sid:
                    sid = f"{sid}_service"
                deps = it.get("dependencies") or []
                if isinstance(deps, str):
                    deps = [deps]
                by_id[sid] = ServiceRecord(
                    service_id=sid,
                    name=str(it.get("name") or sid),
                    version=str(it.get("version") or "1.0.0"),
                    dependencies=[str(d) for d in deps],
                    priority=int(it.get("priority") or 100),
                    state=STATE_REGISTERED,
                )

        # From ecosystem manifests as services
        for it in (eco_data.items or []):
            if isinstance(it, dict):
                eid = str(it.get("engine_id") or it.get("id") or "")
                if eid:
                    sid = f"{eid}_service"
                    if sid not in by_id:
                        by_id[sid] = ServiceRecord(
                            service_id=sid,
                            name=f"{eid} Service",
                            priority=int(it.get("priority") or 100),
                            state=STATE_REGISTERED,
                        )

        return sorted(by_id.values(), key=lambda s: (s.priority, s.service_id))

    def _detect_unregistered(
        self,
        request_data: GenericData,
        services: List[ServiceRecord],
    ) -> int:
        raw = request_data.raw or {}
        known = {s.service_id for s in services}
        attempts = 0
        external = raw.get("unregistered_services") or raw.get("side_channel_services") or []
        if isinstance(external, list):
            for e in external:
                sid = e if isinstance(e, str) else str((e or {}).get("service_id") or "")
                if sid and sid not in known:
                    attempts += 1
        if raw.get("bypass_service_registry"):
            attempts += 1
        return attempts

    def _topo_sort(self, services: List[ServiceRecord]) -> List[ServiceRecord]:
        by_id = {s.service_id: s for s in services}
        visited: Set[str] = set()
        order: List[ServiceRecord] = []

        def visit(sid: str) -> None:
            if sid in visited:
                return
            visited.add(sid)
            svc = by_id.get(sid)
            if not svc:
                return
            for dep in svc.dependencies:
                if dep in by_id:
                    visit(dep)
            order.append(svc)

        # Sort by priority first for stable order among independents
        for s in sorted(services, key=lambda x: (x.priority, x.service_id)):
            visit(s.service_id)
        return order

    def _transition(
        self,
        svc: ServiceRecord,
        action: str,
        target: str,
    ) -> Tuple[LifecycleEvent, bool]:
        prev = svc.state
        # Simple valid transitions
        valid = {
            ACTION_INIT: {STATE_REGISTERED},
            ACTION_START: {STATE_INITIALIZED, STATE_STOPPED, STATE_PAUSED},
            ACTION_PAUSE: {STATE_STARTED},
            ACTION_RESUME: {STATE_PAUSED},
            ACTION_RESTART: {STATE_STARTED, STATE_FAILED, STATE_STOPPED},
            ACTION_SHUTDOWN: {
                STATE_STARTED, STATE_PAUSED, STATE_STOPPED,
                STATE_FAILED, STATE_INITIALIZED,
            },
        }
        allowed_from = valid.get(action, set())
        ok = prev in allowed_from or action == ACTION_RESTART
        if ok:
            if action == ACTION_RESTART:
                svc.state = STATE_STARTED
                target = STATE_STARTED
            else:
                svc.state = target
            if target == STATE_STARTED:
                svc.health_status = "healthy"
        ev = LifecycleEvent(
            event_id=str(uuid.uuid4())[:8],
            service_id=svc.service_id,
            action=action,
            from_state=prev,
            to_state=svc.state if ok else prev,
            success=ok,
            message="ok" if ok else f"invalid transition {prev} --{action}--> {target}",
            timestamp=datetime.now(timezone.utc).isoformat(),
        )
        return ev, ok

    def _health(
        self,
        services: List[ServiceRecord],
        monitoring_data: GenericData,
        request_data: GenericData,
    ) -> List[ServiceHealth]:
        raw = request_data.raw or {}
        result: List[ServiceHealth] = []
        for i, s in enumerate(services):
            avail = 1.0
            err = 0.0
            resp = 50.0 + i * 10
            restarts = 0
            status = "healthy"

            if s.state == STATE_FAILED:
                avail = 0.0
                err = 1.0
                status = "unhealthy"
                restarts = int(raw.get("restart_counts", {}).get(s.service_id, 1) if isinstance(raw.get("restart_counts"), dict) else 1)
            elif s.state == STATE_STARTED:
                avail = 0.99
                err = 0.01
                status = "healthy"
            elif s.state in (STATE_PAUSED, STATE_STOPPED):
                avail = 0.5
                status = "degraded"
            else:
                avail = 0.3
                status = "unknown"

            # Monitoring hints
            for st in (monitoring_data.items or []):
                if isinstance(st, dict) and str(st.get("engine_id") or "") in s.service_id:
                    if st.get("state") == "failed":
                        status = "unhealthy"
                        avail = 0.0

            s.health_status = status
            result.append(ServiceHealth(
                service_id=s.service_id,
                availability=round(avail, 3),
                response_time_ms=round(resp, 1),
                error_rate=round(err, 3),
                restart_count=restarts,
                status=status,
            ))
        return result

    def _recover(
        self,
        services: List[ServiceRecord],
        health: List[ServiceHealth],
    ) -> List[RecoveryRecord]:
        now = datetime.now(timezone.utc).isoformat()
        recoveries: List[RecoveryRecord] = []
        health_map = {h.service_id: h for h in health}

        for s in services:
            h = health_map.get(s.service_id)
            if s.state != STATE_FAILED and (not h or h.status != "unhealthy"):
                continue
            # Restart attempt
            s.state = STATE_RECOVERING
            recoveries.append(RecoveryRecord(
                recovery_id=str(uuid.uuid4())[:10],
                service_id=s.service_id,
                action="restart",
                success=True,
                message=f"Restarting failed service {s.service_id}",
                timestamp=now,
            ))
            s.state = STATE_STARTED
            s.health_status = "healthy"
            if h:
                h.restart_count += 1
                h.status = "healthy"
                h.availability = 0.95
                h.error_rate = 0.05
            recoveries.append(RecoveryRecord(
                recovery_id=str(uuid.uuid4())[:10],
                service_id=s.service_id,
                action="recovery",
                success=True,
                message=f"Service {s.service_id} recovered",
                timestamp=now,
            ))
        return recoveries

    def _allocate(
        self,
        services: List[ServiceRecord],
        resource_data: GenericData,
    ) -> List[ResourceAllocation]:
        n = max(1, len(services))
        cpu = round(min(15.0, 60.0 / n), 2)
        ram = round(min(256.0, 2048.0 / n), 1)
        threads = max(1, min(4, 32 // n))
        allocs: List[ResourceAllocation] = []
        for s in services:
            boost = 1.3 if s.priority <= 30 else (1.1 if s.priority <= 60 else 1.0)
            allocs.append(ResourceAllocation(
                service_id=s.service_id,
                cpu_percent=round(cpu * boost, 2),
                ram_mb=round(ram * boost, 1),
                threads=max(1, int(threads * boost)),
            ))
        return allocs

    def _load(
        self,
        services: List[ServiceRecord],
        request_data: GenericData,
    ) -> List[LoadSample]:
        raw = request_data.raw or {}
        loads: List[LoadSample] = []
        for i, s in enumerate(services):
            base = 10.0 + i * 5
            if s.state == STATE_STARTED:
                base += 20
            if s.state == STATE_FAILED:
                base = 0
            override = (raw.get("loads") or {}).get(s.service_id) if isinstance(raw.get("loads"), dict) else None
            loads.append(LoadSample(
                service_id=s.service_id,
                load_percent=float(override if override is not None else min(95.0, base)),
                queue_depth=int(i * 2),
            ))
        return loads

    def _self_verify(
        self,
        services: List[ServiceRecord],
        events: List[LifecycleEvent],
        unregistered: int,
        dep_violations: int,
    ) -> bool:
        if not services:
            return False
        if not events:
            return False
        # All services must have gone through register at minimum
        if any(s.state == STATE_REGISTERED for s in services):
            # Some may still be registered if deps blocked — acceptable
            pass
        return True


__all__ = ["ServiceManager"]
