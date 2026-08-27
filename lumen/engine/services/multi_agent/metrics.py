"""Phase E — in-process metrics for multi-agent orchestration (no external deps)."""
from __future__ import annotations

import threading
import time
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any



class MetricsRegistry:
    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._counters: dict[str, float] = defaultdict(float)
        self._gauges: dict[str, float] = {}
        self._latency_sum: dict[str, float] = defaultdict(float)
        self._latency_count: dict[str, int] = defaultdict(int)
        self._latency_max: dict[str, float] = defaultdict(float)
        self._started_at = time.time()

    def incr(self, name: str, value: float = 1.0, **labels: str) -> None:
        key = self._key(name, labels)
        with self._lock:
            self._counters[key] += value

    def gauge(self, name: str, value: float, **labels: str) -> None:
        key = self._key(name, labels)
        with self._lock:
            self._gauges[key] = value

    def observe(self, name: str, seconds: float, **labels: str) -> None:
        key = self._key(name, labels)
        with self._lock:
            self._latency_sum[key] += max(0.0, seconds)
            self._latency_count[key] += 1
            if seconds > self._latency_max[key]:
                self._latency_max[key] = seconds

    def timer(self, name: str, **labels: str) -> "_TimerCtx":
        return _TimerCtx(self, name, labels)

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            lat: dict[str, Any] = {}
            for k, total in self._latency_sum.items():
                n = max(1, self._latency_count[k])
                lat[k] = {
                    "count": self._latency_count[k],
                    "sum_s": round(total, 4),
                    "avg_s": round(total / n, 4),
                    "max_s": round(self._latency_max[k], 4),
                }
            return {
                "uptime_s": round(time.time() - self._started_at, 2),
                "counters": dict(self._counters),
                "gauges": dict(self._gauges),
                "latency": lat,
            }

    @staticmethod
    def _key(name: str, labels: dict[str, str]) -> str:
        if not labels:
            return name
        parts = ",".join(f"{k}={v}" for k, v in sorted(labels.items()))
        return f"{name}{{{parts}}}"


class _TimerCtx:
    def __init__(self, reg: MetricsRegistry, name: str, labels: dict[str, str]) -> None:
        self.reg = reg
        self.name = name
        self.labels = labels
        self._t0 = 0.0

    def __enter__(self) -> "_TimerCtx":
        self._t0 = time.time()
        return self

    def __exit__(self, *args: Any) -> None:
        self.reg.observe(self.name, time.time() - self._t0, **self.labels)


_METRICS = MetricsRegistry()


def get_metrics() -> MetricsRegistry:
    return _METRICS


def metrics_snapshot() -> dict[str, Any]:
    return _METRICS.snapshot()


def record_cost_usd(amount: float, **labels: str) -> None:
    """Accumulate estimated LLM/tool cost for Phase D evaluation."""
    get_metrics().incr("cost_usd", float(amount or 0.0), **labels)


def record_eval_outcome(*, success: bool, attempts: int = 1, latency_s: float = 0.0, cost_usd: float = 0.0, platform: str = "") -> None:
    m = get_metrics()
    m.incr("eval_runs", platform=platform or "unknown")
    if success:
        m.incr("eval_success", platform=platform or "unknown")
    else:
        m.incr("eval_failure", platform=platform or "unknown")
    m.observe("eval_latency_s", float(latency_s or 0.0), platform=platform or "unknown")
    if cost_usd:
        record_cost_usd(cost_usd, platform=platform or "unknown")
    m.gauge("eval_last_attempts", float(attempts or 0), platform=platform or "unknown")
