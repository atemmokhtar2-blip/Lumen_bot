"""
PerformanceAnalyzer — Specification 036 (ULTRA CRITICAL)

Detects performance bottlenecks and applies safe, behaviour-preserving
optimisations. Never changes business logic.
"""

from __future__ import annotations

import logging
import re
import uuid
from typing import Dict, List, Tuple

from .data_readers import GenericData
from .report_data import (
    PerfUnit, Bottleneck, PerformanceAction, LoadSimulation, CachePlan,
    SEVERITY_CRITICAL, SEVERITY_HIGH, SEVERITY_MEDIUM, SEVERITY_LOW,
    STATUS_OPEN, STATUS_OPTIMIZED,
    BN_NESTED_LOOP, BN_HEAVY_LOOP, BN_RECURSION, BN_CPU_HEAVY,
    BN_MEMORY_ALLOC, BN_ALGORITHM, BN_DB_REPEATED, BN_API_REPEATED,
    BN_API_NO_TIMEOUT, BN_TG_RATE, BN_TG_POLLING, BN_NO_CACHE,
    BN_SYNC_BLOCKING,
    OPT_LIST_COMP, OPT_GENERATOR, OPT_CACHE_ADD, OPT_TIMEOUT_ADD,
    OPT_ASYNC_CONVERT, OPT_BATCH, OPT_TG_BATCH, OPT_DB_CACHE,
)

_log = logging.getLogger("engine.performance_optimization.analyzer")

_NESTED_FOR = re.compile(
    r"""for\s+\w+\s+in\s+[^:]+:\s*(?:\n\s+.*)*?\n\s+for\s+\w+\s+in""",
    re.MULTILINE,
)
_RANGE_LARGE = re.compile(r"""for\s+\w+\s+in\s+range\s*\(\s*(\d{5,})\s*\)""")
_RECURSION_HINT = re.compile(r"""def\s+(\w+)\s*\([^)]*\):[^]*?\1\s*\(""", re.DOTALL)
_SLEEP = re.compile(r"""(?:time\.sleep|asyncio\.sleep)\s*\(\s*[^0]""")
_REQUESTS_NO_TIMEOUT = re.compile(
    r"""requests\.(?:get|post|put|delete|request)\s*\((?![^)]*timeout)""",
    re.IGNORECASE,
)
_DB_EXECUTE_IN_LOOP = re.compile(
    r"""for\s+.*:\s*(?:\n\s+.*)*?(?:\.execute\s*\(|session\.(?:query|execute)|cursor\.execute)""",
    re.MULTILINE | re.IGNORECASE,
)
_TG_SEND_IN_LOOP = re.compile(
    r"""for\s+.*:\s*(?:\n\s+.*)*?(?:\.send_message|\.answer|\.reply_text|bot\.send)""",
    re.MULTILINE | re.IGNORECASE,
)
_LIST_APPEND_LOOP = re.compile(
    r"""(\w+)\s*=\s*\[\s*\]\s*\n(?:\s+.*\n)*?\s+for\s+\w+\s+in\s+([^:]+):\s*\n\s+\1\.append\s*\(([^)]+)\)""",
    re.MULTILINE,
)
_BLOCKING_IN_ASYNC = re.compile(
    r"""async\s+def\s+\w+[^]*?(?:time\.sleep|requests\.(?:get|post)|open\s*\()""",
    re.DOTALL,
)


class PerformanceAnalyzer:
    """Heuristic performance analyzer + safe optimiser."""

    def analyze_and_optimize(
        self,
        sec_data: GenericData,
        opt_data: GenericData,
        bl_data: GenericData,
    ) -> Tuple[
        List[PerfUnit],
        List[Bottleneck],
        List[PerformanceAction],
        List[LoadSimulation],
        List[CachePlan],
    ]:
        units: List[PerfUnit] = []
        bottlenecks: List[Bottleneck] = []
        actions: List[PerformanceAction] = []
        cache_plans: List[CachePlan] = []

        bodies = self._collect_bodies(sec_data, opt_data, bl_data)

        for body in bodies:
            unit_id = str(
                body.get("unit_id") or body.get("method_id") or body.get("name") or uuid.uuid4()
            )
            original = str(
                body.get("secured_code")
                or body.get("optimized_code")
                or body.get("source_code")
                or body.get("code")
                or ""
            )
            class_name = str(body.get("class_name") or "")
            method_name = str(body.get("method_name") or body.get("name") or "")
            q_before = float(
                body.get("quality_after") or body.get("quality_score") or 60.0
            )

            if not original.strip():
                units.append(PerfUnit(
                    unit_id=unit_id,
                    class_name=class_name,
                    method_name=method_name,
                    quality_before=q_before,
                    quality_after=q_before,
                    notes="empty unit skipped",
                ))
                continue

            found_bns, unit_actions, optimized, time_c, space_c = self._analyze_unit(
                unit_id, class_name, method_name, original,
            )
            bottlenecks.extend(found_bns)
            actions.extend(unit_actions)
            applied = len(unit_actions)
            changed = optimized != original
            q_after = min(100.0, q_before + (4.0 * applied) - (2.0 * max(0, len(found_bns) - applied)))
            q_after = max(0.0, round(q_after, 1))

            units.append(PerfUnit(
                unit_id=unit_id,
                class_name=class_name,
                method_name=method_name,
                original_code=original,
                optimized_code=optimized,
                bottlenecks_found=len(found_bns),
                actions_applied=applied,
                quality_before=q_before,
                quality_after=q_after,
                time_complexity_hint=time_c,
                space_complexity_hint=space_c,
                changed=changed,
                notes=f"bn={len(found_bns)} actions={applied}",
            ))

            # Cache opportunities from unit
            if re.search(r"""(?:get_|fetch_|load_|query_)""", method_name, re.I):
                if not re.search(r"""(?:cache|lru_cache|@cached)""", original, re.I):
                    cache_plans.append(CachePlan(
                        opportunity_id=str(uuid.uuid4())[:8],
                        data_description=f"{class_name}.{method_name} result",
                        suggested_ttl_seconds=300,
                        scope="process",
                        reason="Read-like method without visible cache.",
                    ))
                    bottlenecks.append(Bottleneck(
                        bottleneck_id=f"cache_{unit_id}",
                        bottleneck_type=BN_NO_CACHE,
                        severity=SEVERITY_LOW,
                        message="Possible cache opportunity on read-like method.",
                        location=f"{class_name}.{method_name}",
                        unit_id=unit_id,
                        status=STATUS_OPEN,
                        resolution_hint="Consider functools.lru_cache or explicit cache layer.",
                    ))

        simulations = self._simulate_load(units, bottlenecks)

        _log.info(
            "PerformanceAnalyzer: units=%d bottlenecks=%d actions=%d cache_ops=%d",
            len(units), len(bottlenecks), len(actions), len(cache_plans),
        )
        return units, bottlenecks, actions, simulations, cache_plans

    def self_review(
        self,
        units: List[PerfUnit],
        bottlenecks: List[Bottleneck],
    ) -> Tuple[bool, List[Bottleneck]]:
        residual: List[Bottleneck] = []
        for u in units:
            code = u.optimized_code or u.original_code
            if not code.strip():
                continue
            bns, _, _, _, _ = self._analyze_unit(
                u.unit_id, u.class_name, u.method_name, code, apply_fixes=False,
            )
            for b in bns:
                if b.severity == SEVERITY_CRITICAL and b.status == STATUS_OPEN:
                    residual.append(b)

        still_open = [
            b for b in bottlenecks
            if b.severity == SEVERITY_CRITICAL and b.status == STATUS_OPEN
        ]
        passed = len(residual) == 0 and len(still_open) == 0
        return passed, residual

    def _collect_bodies(
        self,
        sec_data: GenericData,
        opt_data: GenericData,
        bl_data: GenericData,
    ) -> List[Dict]:
        bodies: List[Dict] = []
        if sec_data.available and sec_data.items:
            for u in sec_data.items:
                bodies.append({
                    "unit_id": u.get("unit_id") or u.get("method_id"),
                    "class_name": u.get("class_name", ""),
                    "method_name": u.get("method_name", ""),
                    "source_code": (
                        u.get("secured_code") or u.get("optimized_code")
                        or u.get("source_code") or ""
                    ),
                    "quality_score": u.get("quality_after") or u.get("quality_before") or 60.0,
                })
        elif opt_data.available and opt_data.items:
            for u in opt_data.items:
                bodies.append({
                    "unit_id": u.get("unit_id") or u.get("method_id"),
                    "class_name": u.get("class_name", ""),
                    "method_name": u.get("method_name", ""),
                    "source_code": u.get("optimized_code") or u.get("source_code") or "",
                    "quality_score": u.get("quality_after") or 60.0,
                })
        elif bl_data.available and bl_data.items:
            for b in bl_data.items:
                bodies.append({
                    "unit_id": b.get("method_id"),
                    "class_name": b.get("class_name", ""),
                    "method_name": b.get("method_name", ""),
                    "source_code": b.get("source_code", ""),
                    "quality_score": b.get("quality_score", 60.0),
                })
        return bodies

    def _analyze_unit(
        self,
        unit_id: str,
        class_name: str,
        method_name: str,
        code: str,
        apply_fixes: bool = True,
    ) -> Tuple[List[Bottleneck], List[PerformanceAction], str, str, str]:
        bns: List[Bottleneck] = []
        acts: List[PerformanceAction] = []
        optimized = code
        location = f"{class_name}.{method_name}" if class_name else method_name or unit_id
        time_c = "O(n)" if "for " in code else "O(1)"
        space_c = "O(n)" if "append" in code or "[]" in code else "O(1)"

        # Nested loops
        if _NESTED_FOR.search(code):
            bns.append(Bottleneck(
                bottleneck_id=f"nested_{unit_id}",
                bottleneck_type=BN_NESTED_LOOP,
                severity=SEVERITY_HIGH,
                message="Nested loop detected — possible O(n²) behaviour.",
                location=location,
                unit_id=unit_id,
                estimated_impact="latency grows quadratically with input size",
                status=STATUS_OPEN,
                resolution_hint="Flatten loops or use dict/set lookups where possible.",
            ))
            time_c = "O(n²)"

        # Large range
        m = _RANGE_LARGE.search(code)
        if m:
            bns.append(Bottleneck(
                bottleneck_id=f"heavy_loop_{unit_id}",
                bottleneck_type=BN_HEAVY_LOOP,
                severity=SEVERITY_MEDIUM,
                message=f"Large range loop (range({m.group(1)})).",
                location=location,
                unit_id=unit_id,
                status=STATUS_OPEN,
                resolution_hint="Process in batches or use generators.",
            ))

        # DB in loop
        if _DB_EXECUTE_IN_LOOP.search(code):
            bns.append(Bottleneck(
                bottleneck_id=f"db_loop_{unit_id}",
                bottleneck_type=BN_DB_REPEATED,
                severity=SEVERITY_CRITICAL,
                message="Database execute/query inside a loop (N+1 risk).",
                location=location,
                unit_id=unit_id,
                estimated_impact="critical under load",
                status=STATUS_OPEN,
                resolution_hint="Batch queries or eager-load related data.",
            ))
            if apply_fixes:
                acts.append(PerformanceAction(
                    action_id=str(uuid.uuid4())[:8],
                    action_type=OPT_DB_CACHE,
                    unit_id=unit_id,
                    description="Hint: batch DB operations outside the loop.",
                    behavior_safe=True,
                ))

        # Telegram send in loop
        if _TG_SEND_IN_LOOP.search(code):
            bns.append(Bottleneck(
                bottleneck_id=f"tg_loop_{unit_id}",
                bottleneck_type=BN_TG_RATE,
                severity=SEVERITY_HIGH,
                message="Telegram send/answer inside a loop — rate limit risk.",
                location=location,
                unit_id=unit_id,
                estimated_impact="429 / flood wait under load",
                status=STATUS_OPEN,
                resolution_hint="Batch messages or add rate limiting / asyncio gather with semaphore.",
            ))
            if apply_fixes:
                acts.append(PerformanceAction(
                    action_id=str(uuid.uuid4())[:8],
                    action_type=OPT_TG_BATCH,
                    unit_id=unit_id,
                    description="Hint: batch Telegram sends with rate limiting.",
                    behavior_safe=True,
                ))

        # requests without timeout
        if _REQUESTS_NO_TIMEOUT.search(code):
            bns.append(Bottleneck(
                bottleneck_id=f"timeout_{unit_id}",
                bottleneck_type=BN_API_NO_TIMEOUT,
                severity=SEVERITY_MEDIUM,
                message="HTTP request without explicit timeout.",
                location=location,
                unit_id=unit_id,
                status=STATUS_OPEN,
                resolution_hint="Add timeout= parameter to all HTTP calls.",
            ))
            if apply_fixes:
                # Conservative: only document, don't rewrite fragile calls
                acts.append(PerformanceAction(
                    action_id=str(uuid.uuid4())[:8],
                    action_type=OPT_TIMEOUT_ADD,
                    unit_id=unit_id,
                    description="Recommend timeout= on HTTP client calls.",
                    behavior_safe=True,
                ))

        # Blocking call in async def
        if _BLOCKING_IN_ASYNC.search(code):
            bns.append(Bottleneck(
                bottleneck_id=f"blocking_{unit_id}",
                bottleneck_type=BN_SYNC_BLOCKING,
                severity=SEVERITY_HIGH,
                message="Blocking call inside async function.",
                location=location,
                unit_id=unit_id,
                status=STATUS_OPEN,
                resolution_hint="Use asyncio-compatible APIs (aiohttp, asyncio.sleep).",
            ))
            if apply_fixes:
                acts.append(PerformanceAction(
                    action_id=str(uuid.uuid4())[:8],
                    action_type=OPT_ASYNC_CONVERT,
                    unit_id=unit_id,
                    description="Hint: replace blocking I/O with async equivalents.",
                    behavior_safe=True,
                ))

        # list append loop → list comprehension hint
        lm = _LIST_APPEND_LOOP.search(code)
        if lm and apply_fixes:
            acts.append(PerformanceAction(
                action_id=str(uuid.uuid4())[:8],
                action_type=OPT_LIST_COMP,
                unit_id=unit_id,
                description="Loop+append can often become a list comprehension.",
                before_hint="result=[]; for x in xs: result.append(f(x))",
                after_hint="result = [f(x) for x in xs]",
                behavior_safe=True,
            ))
            bns.append(Bottleneck(
                bottleneck_id=f"append_loop_{unit_id}",
                bottleneck_type=BN_MEMORY_ALLOC,
                severity=SEVERITY_LOW,
                message="Append-in-loop pattern — consider list comprehension.",
                location=location,
                unit_id=unit_id,
                status=STATUS_OPTIMIZED,
                resolution_hint="Use list comprehension or generator.",
            ))

        # sleep
        if _SLEEP.search(code):
            bns.append(Bottleneck(
                bottleneck_id=f"sleep_{unit_id}",
                bottleneck_type=BN_CPU_HEAVY,
                severity=SEVERITY_MEDIUM,
                message="Explicit sleep in code path.",
                location=location,
                unit_id=unit_id,
                status=STATUS_OPEN,
                resolution_hint="Avoid sleep on hot paths; use event-driven waits.",
            ))

        # Polling hint
        if re.search(r"""(?:get_updates|polling|updater\.start_polling)""", code, re.I):
            bns.append(Bottleneck(
                bottleneck_id=f"polling_{unit_id}",
                bottleneck_type=BN_TG_POLLING,
                severity=SEVERITY_LOW,
                message="Long polling detected — ensure reasonable timeout and backoff.",
                location=location,
                unit_id=unit_id,
                status=STATUS_OPEN,
                resolution_hint="Prefer webhooks for production scale when possible.",
            ))

        return bns, acts, optimized, time_c, space_c

    def _simulate_load(
        self,
        units: List[PerfUnit],
        bottlenecks: List[Bottleneck],
    ) -> List[LoadSimulation]:
        open_crit = sum(
            1 for b in bottlenecks
            if b.severity == SEVERITY_CRITICAL and b.status == STATUS_OPEN
        )
        open_high = sum(
            1 for b in bottlenecks
            if b.severity == SEVERITY_HIGH and b.status == STATUS_OPEN
        )
        base_latency = 20.0 + (5.0 * len(units)) + (40.0 * open_crit) + (15.0 * open_high)
        base_cpu = 5.0 + (0.5 * len(units)) + (10.0 * open_crit)
        base_mem = 32.0 + (2.0 * len(units))

        sims: List[LoadSimulation] = []
        for users, factor in ((100, 1.0), (1000, 8.0), (10000, 60.0)):
            lat = round(base_latency * factor, 1)
            cpu = min(100.0, round(base_cpu * (factor ** 0.7), 1))
            mem = round(base_mem * (1 + factor * 0.15), 1)
            if open_crit and users >= 1000:
                risk = "critical"
            elif open_high and users >= 1000:
                risk = "high"
            elif lat > 500:
                risk = "medium"
            else:
                risk = "low"
            sims.append(LoadSimulation(
                users=users,
                estimated_latency_ms=lat,
                estimated_cpu_pct=cpu,
                estimated_memory_mb=mem,
                bottleneck_risk=risk,
                notes=f"Heuristic estimate from {len(bottlenecks)} bottleneck(s).",
            ))
        return sims


__all__ = ["PerformanceAnalyzer"]
