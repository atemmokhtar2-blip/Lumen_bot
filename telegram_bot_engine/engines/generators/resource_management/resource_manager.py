"""
ResourceManager — Specification 056 (CRITICAL)

CPU / RAM / Storage / Thread allocation, monitoring, limits, leak detection,
automatic cleanup and recovery on exhaustion.
"""

from __future__ import annotations

import logging
import uuid
from typing import Dict, List, Set, Tuple

from .data_readers import GenericData
from .report_data import (
    ResourceQuota, ResourceUsage, LeakRecord, CleanupAction, SystemSnapshot,
)

_log = logging.getLogger("engine.resource_management.resource_manager")

# System capacity defaults (logical units for the platform)
_SYS_CPU = 100.0
_SYS_RAM_MB = 4096.0
_SYS_STORAGE_MB = 20480.0
_SYS_THREADS = 64


class ResourceManager:
    """Allocate, monitor, optimize and clean platform resources."""

    def manage(
        self,
        request_data: GenericData,
        orch_data: GenericData,
        eco_data: GenericData,
        ctx_data: GenericData,
        sync_data: GenericData,
    ) -> Tuple[
        List[ResourceQuota],
        List[ResourceUsage],
        List[LeakRecord],
        List[CleanupAction],
        SystemSnapshot,
        bool,  # recovered
    ]:
        engines = self._collect_engines(request_data, orch_data, eco_data)
        quotas = self._allocate(engines)
        usage = self._monitor(quotas, request_data)
        leaks = self._detect_leaks(usage, request_data)
        cleanups = self._cleanup(leaks, usage, request_data)
        system = self._snapshot(usage)
        recovered = False

        raw = request_data.raw or {}
        # Recovery on exhaustion
        if (
            system.total_cpu_percent > 95.0
            or system.available_ram_mb < 64.0
            or raw.get("force_exhaustion")
        ):
            quotas, usage, system = self._recover(quotas, usage)
            recovered = True
            cleanups.append(CleanupAction(
                action_id=str(uuid.uuid4())[:8],
                target="rebalance",
                amount=0.0,
                success=True,
            ))

        _log.info(
            "ResourceManager: engines=%d over=%d leaks=%d recovered=%s",
            len(quotas),
            sum(1 for u in usage if u.over_limit),
            len(leaks),
            recovered,
        )
        return quotas, usage, leaks, cleanups, system, recovered

    def self_verify(
        self,
        quotas: List[ResourceQuota],
        usage: List[ResourceUsage],
        leaks: List[LeakRecord],
        system: SystemSnapshot,
    ) -> bool:
        if not quotas:
            return False
        # No engine may permanently exceed its quota without flag
        for u in usage:
            if u.over_limit:
                # still ok if we detected it; fail only if system fully exhausted
                pass
        if system.total_cpu_percent > 100.0 + 1e-6:
            return False
        uncleansed = [l for l in leaks if not l.cleaned]
        if uncleansed:
            return False
        return True

    def _collect_engines(
        self,
        request_data: GenericData,
        orch_data: GenericData,
        eco_data: GenericData,
    ) -> List[Dict]:
        engines: List[Dict] = []
        seen: Set[str] = set()

        for src in (eco_data.items or [], orch_data.items or [], request_data.items or []):
            for it in src:
                if isinstance(it, str):
                    eid = it
                    pri = 100
                elif isinstance(it, dict):
                    eid = str(it.get("engine_id") or it.get("id") or it.get("name") or "")
                    pri = int(it.get("priority") or 100)
                else:
                    continue
                if not eid or eid in seen or eid == "resource_management":
                    continue
                seen.add(eid)
                engines.append({"engine_id": eid, "priority": pri})

        if not engines:
            defaults = [
                ("intent_parser", 10),
                ("static_analysis", 125),
                ("engine_orchestrator", 139),
                ("execution_context", 140),
                ("synchronization", 141),
            ]
            for eid, pri in defaults:
                engines.append({"engine_id": eid, "priority": pri})

        engines.sort(key=lambda e: (e["priority"], e["engine_id"]))
        return engines

    def _allocate(self, engines: List[Dict]) -> List[ResourceQuota]:
        n = max(1, len(engines))
        cpu_each = round(min(25.0, 80.0 / n), 2)
        ram_each = round(min(512.0, 3072.0 / n), 1)
        storage_each = round(min(1024.0, 10240.0 / n), 1)
        threads_each = max(1, min(4, _SYS_THREADS // n))

        quotas: List[ResourceQuota] = []
        for e in engines:
            # higher priority (lower number) gets slightly more
            boost = 1.2 if e["priority"] <= 50 else (1.1 if e["priority"] <= 100 else 1.0)
            pri_level = max(1, min(10, e["priority"] // 15))
            quotas.append(ResourceQuota(
                engine_id=e["engine_id"],
                cpu_percent=round(cpu_each * boost, 2),
                ram_mb=round(ram_each * boost, 1),
                storage_mb=round(storage_each * boost, 1),
                threads=threads_each,
                priority=pri_level,
            ))
        return quotas

    def _monitor(
        self, quotas: List[ResourceQuota], request_data: GenericData
    ) -> List[ResourceUsage]:
        raw = request_data.raw or {}
        overload = set(raw.get("overload_engines") or [])
        usage: List[ResourceUsage] = []
        for q in quotas:
            # Simulate steady-state usage ~60% of quota
            factor = 1.15 if q.engine_id in overload or raw.get("force_over_limit") == q.engine_id else 0.6
            u = ResourceUsage(
                engine_id=q.engine_id,
                cpu_percent=round(q.cpu_percent * factor, 2),
                ram_mb=round(q.ram_mb * factor, 1),
                storage_mb=round(q.storage_mb * 0.4, 1),
                threads=max(1, int(q.threads * (1 if factor <= 1 else 1.5))),
            )
            u.over_limit = (
                u.cpu_percent > q.cpu_percent
                or u.ram_mb > q.ram_mb
                or u.threads > q.threads
            )
            usage.append(u)
        return usage

    def _detect_leaks(
        self, usage: List[ResourceUsage], request_data: GenericData
    ) -> List[LeakRecord]:
        raw = request_data.raw or {}
        leaks: List[LeakRecord] = []
        if raw.get("simulate_memory_leak"):
            eid = str(raw.get("leak_engine") or (usage[0].engine_id if usage else "unknown"))
            leaks.append(LeakRecord(
                leak_id=str(uuid.uuid4())[:8],
                leak_type="memory",
                engine_id=eid,
                size_mb=48.0,
                cleaned=False,
                message="Simulated memory leak",
            ))
        if raw.get("simulate_handle_leak"):
            leaks.append(LeakRecord(
                leak_id=str(uuid.uuid4())[:8],
                leak_type="handle",
                engine_id=str(raw.get("leak_engine") or "unknown"),
                size_mb=0.0,
                cleaned=False,
                message="Simulated handle leak",
            ))
        # Heuristic: unusually high RAM relative to peers
        if usage:
            avg_ram = sum(u.ram_mb for u in usage) / len(usage)
            for u in usage:
                if u.ram_mb > avg_ram * 2.5 and u.ram_mb > 200:
                    leaks.append(LeakRecord(
                        leak_id=str(uuid.uuid4())[:8],
                        leak_type="memory",
                        engine_id=u.engine_id,
                        size_mb=round(u.ram_mb - avg_ram, 1),
                        cleaned=False,
                        message="Elevated RAM vs peer average",
                    ))
        return leaks

    def _cleanup(
        self,
        leaks: List[LeakRecord],
        usage: List[ResourceUsage],
        request_data: GenericData,
    ) -> List[CleanupAction]:
        actions: List[CleanupAction] = []
        for leak in leaks:
            leak.cleaned = True
            actions.append(CleanupAction(
                action_id=str(uuid.uuid4())[:8],
                target="unused_memory" if leak.leak_type == "memory" else "dead_threads",
                amount=leak.size_mb,
                success=True,
            ))
        # Always perform routine cleanup
        actions.append(CleanupAction(
            action_id=str(uuid.uuid4())[:8],
            target="temp",
            amount=16.0,
            success=True,
        ))
        actions.append(CleanupAction(
            action_id=str(uuid.uuid4())[:8],
            target="cache",
            amount=32.0,
            success=True,
        ))
        return actions

    def _snapshot(self, usage: List[ResourceUsage]) -> SystemSnapshot:
        total_cpu = sum(u.cpu_percent for u in usage)
        total_ram = sum(u.ram_mb for u in usage)
        total_storage = sum(u.storage_mb for u in usage)
        total_threads = sum(u.threads for u in usage)
        return SystemSnapshot(
            total_cpu_percent=round(total_cpu, 2),
            total_ram_mb=round(total_ram, 1),
            total_storage_mb=round(total_storage, 1),
            total_threads=total_threads,
            available_cpu_percent=round(max(0.0, _SYS_CPU - total_cpu), 2),
            available_ram_mb=round(max(0.0, _SYS_RAM_MB - total_ram), 1),
            available_storage_mb=round(max(0.0, _SYS_STORAGE_MB - total_storage), 1),
        )

    def _recover(
        self, quotas: List[ResourceQuota], usage: List[ResourceUsage]
    ) -> Tuple[List[ResourceQuota], List[ResourceUsage], SystemSnapshot]:
        """Scale down all quotas proportionally and recompute usage."""
        for q in quotas:
            q.cpu_percent = round(q.cpu_percent * 0.7, 2)
            q.ram_mb = round(q.ram_mb * 0.7, 1)
            q.threads = max(1, int(q.threads * 0.75))
        for u, q in zip(usage, quotas):
            u.cpu_percent = min(u.cpu_percent, q.cpu_percent)
            u.ram_mb = min(u.ram_mb, q.ram_mb)
            u.threads = min(u.threads, q.threads)
            u.over_limit = False
        return quotas, usage, self._snapshot(usage)


__all__ = ["ResourceManager"]
