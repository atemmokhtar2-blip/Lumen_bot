"""Prometheus /metrics exposition via official prometheus_client."""
from __future__ import annotations

import logging

logger = logging.getLogger("lumen.metrics")


def prometheus_available() -> bool:
    try:
        import prometheus_client  # noqa: F401
        return True
    except ImportError:
        return False


def metrics_payload() -> tuple[bytes, str]:
    """Return (body, content_type) for GET /metrics."""
    from prometheus_client import CONTENT_TYPE_LATEST, generate_latest, REGISTRY
    return generate_latest(REGISTRY), CONTENT_TYPE_LATEST


def instrument_app_middleware():
    """Optional aiohttp middleware factory counting requests."""
    try:
        from prometheus_client import Counter, Histogram
    except ImportError:
        return None

    reqs = Counter(
        "lumen_http_requests_total",
        "HTTP requests",
        ["method", "path", "status"],
    )
    latency = Histogram(
        "lumen_http_request_duration_seconds",
        "Request latency",
        ["method", "path"],
        buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10),
    )

    @web_middleware_safe
    async def middleware(request, handler):
        import time
        start = time.perf_counter()
        path = request.path
        # low-cardinality: collapse ids
        for prefix in ("/v1/jobs/", "/v1/admin/credits/"):
            if path.startswith(prefix) and path != prefix.rstrip("/"):
                path = prefix + ":id"
                break
        try:
            resp = await handler(request)
            status = getattr(resp, "status", 500)
            return resp
        except Exception:
            status = 500
            raise
        finally:
            elapsed = time.perf_counter() - start
            try:
                reqs.labels(request.method, path, str(status)).inc()
                latency.labels(request.method, path).observe(elapsed)
            except Exception:
                pass

    return middleware


def web_middleware_safe(fn):
    """Mark as aiohttp middleware without importing aiohttp at module load."""
    try:
        from aiohttp.web import middleware
        return middleware(fn)
    except Exception:
        return fn
