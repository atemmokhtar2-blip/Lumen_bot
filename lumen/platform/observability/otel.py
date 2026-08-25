"""OpenTelemetry traces + metrics (official SDK).

OTLP HTTP exporter is the standard path to collectors (Grafana Alloy, Datadog
agent, Cloud Trace, etc.). Missing packages → no-op (local dev still works).
"""
from __future__ import annotations

import logging
import os
from typing import Any

logger = logging.getLogger("lumen.otel")

_tracer_provider: Any = None
_meter_provider: Any = None


def _service_name(explicit: str | None = None) -> str:
    return (
        (explicit or "").strip()
        or (os.getenv("OTEL_SERVICE_NAME") or "").strip()
        or (os.getenv("SERVICE_NAME") or "").strip()
        or "lumen"
    )


def _exporter_wanted(kind: str) -> str:
    """Return otlp|prometheus|none for traces or metrics."""
    key = f"OTEL_{kind.upper()}_EXPORTER"
    raw = (os.getenv(key) or "").strip().lower()
    if raw:
        return raw
    # Auto: enable OTLP when endpoint is set
    if (os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT") or os.getenv("OTEL_EXPORTER_OTLP_TRACES_ENDPOINT") or "").strip():
        return "otlp"
    return "none"


def setup_otel(*, service_name: str | None = None) -> None:
    global _tracer_provider, _meter_provider
    name = _service_name(service_name)
    try:
        from opentelemetry import trace, metrics
        from opentelemetry.sdk.resources import Resource, SERVICE_NAME
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor
        from opentelemetry.sdk.metrics import MeterProvider
        from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
    except ImportError:
        logger.info("opentelemetry SDK not installed — tracing disabled")
        return

    resource = Resource.create({SERVICE_NAME: name})

    # ── Traces ──────────────────────────────────────────────────────
    traces_exp = _exporter_wanted("traces")
    if traces_exp == "otlp":
        try:
            from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
            provider = TracerProvider(resource=resource)
            provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter()))
            trace.set_tracer_provider(provider)
            _tracer_provider = provider
            logger.info("OTEL traces → OTLP (%s)", name)
        except Exception:
            logger.exception("OTEL traces exporter failed")
    else:
        # Still set a provider so get_tracer works (no export)
        provider = TracerProvider(resource=resource)
        trace.set_tracer_provider(provider)
        _tracer_provider = provider

    # ── Metrics ─────────────────────────────────────────────────────
    metrics_exp = _exporter_wanted("metrics")
    readers = []
    if metrics_exp == "otlp":
        try:
            from opentelemetry.exporter.otlp.proto.http.metric_exporter import OTLPMetricExporter
            readers.append(PeriodicExportingMetricReader(OTLPMetricExporter()))
        except Exception:
            logger.exception("OTEL metrics OTLP exporter failed")
    if metrics_exp == "prometheus" or (os.getenv("OTEL_METRICS_PROM") or "").strip().lower() in {"1", "true"}:
        try:
            from opentelemetry.exporter.prometheus import PrometheusMetricReader
            readers.append(PrometheusMetricReader())
        except Exception:
            logger.info("prometheus OTEL reader unavailable; use prometheus_client /metrics")
    if readers:
        mprov = MeterProvider(resource=resource, metric_readers=readers)
        metrics.set_meter_provider(mprov)
        _meter_provider = mprov
        logger.info("OTEL metrics exporters=%s", metrics_exp)


def get_tracer(name: str = "lumen"):
    try:
        from opentelemetry import trace
        return trace.get_tracer(name)
    except ImportError:
        return _NoopTracer()


def get_meter(name: str = "lumen"):
    try:
        from opentelemetry import metrics
        return metrics.get_meter(name)
    except ImportError:
        return _NoopMeter()


def shutdown_otel() -> None:
    global _tracer_provider, _meter_provider
    for prov in (_tracer_provider, _meter_provider):
        if prov is None:
            continue
        try:
            prov.shutdown()
        except Exception:
            logger.exception("otel shutdown failed")
    _tracer_provider = None
    _meter_provider = None


class _NoopSpan:
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def set_attribute(self, *a, **k):
        pass

    def record_exception(self, *a, **k):
        pass


class _NoopTracer:
    def start_as_current_span(self, *a, **k):
        return _NoopSpan()


class _NoopMeter:
    def create_counter(self, *a, **k):
        return _NoopInstrument()

    def create_histogram(self, *a, **k):
        return _NoopInstrument()


class _NoopInstrument:
    def add(self, *a, **k):
        pass

    def record(self, *a, **k):
        pass
