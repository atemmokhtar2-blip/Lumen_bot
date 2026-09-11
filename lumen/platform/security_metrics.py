"""In-process + Prometheus counters for security events (Phase E).

Every watched security event increments a counter so ops can scrape /metrics
or read process stats without relying solely on log shipping.
"""
from __future__ import annotations

import logging
import threading
from typing import Any

logger = logging.getLogger("lumen.platform.security_metrics")

_lock = threading.Lock()
_COUNTS: dict[str, int] = {}
_PROM: dict[str, Any] = {}


def _prom_counter(event_type: str):
    try:
        from prometheus_client import Counter
    except Exception:
        return None
    if "security_events_total" not in _PROM:
        try:
            _PROM["security_events_total"] = Counter(
                "lumen_security_events_total",
                "Security events by type",
                ["event_type", "severity"],
            )
        except Exception:
            return None
    return _PROM.get("security_events_total")


def record_security_event(event_type: str, severity: str = "warning") -> int:
    """Increment counters; return new in-process count for this event_type."""
    et = (event_type or "unknown").strip() or "unknown"
    sev = (severity or "warning").strip() or "warning"
    with _lock:
        _COUNTS[et] = int(_COUNTS.get(et, 0)) + 1
        n = _COUNTS[et]
    try:
        c = _prom_counter(et)
        if c is not None:
            c.labels(event_type=et[:80], severity=sev[:20]).inc()
    except Exception:
        logger.debug("prom_security_counter_failed", exc_info=True)
    return n


def snapshot() -> dict[str, int]:
    with _lock:
        return dict(_COUNTS)


def reset_for_tests() -> None:
    with _lock:
        _COUNTS.clear()


__all__ = ["record_security_event", "snapshot", "reset_for_tests"]
