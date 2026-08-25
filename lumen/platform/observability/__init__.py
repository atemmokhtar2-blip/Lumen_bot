"""World-class observability: structured JSON logs + OpenTelemetry + Prometheus.

Enable via env (all optional, fail-open for local dev):

  OTEL_SERVICE_NAME=lumen-api
  OTEL_EXPORTER_OTLP_ENDPOINT=http://otel-collector:4318
  OTEL_TRACES_EXPORTER=otlp          # or none
  OTEL_METRICS_EXPORTER=otlp|prometheus|none
  LOG_FORMAT=json|text               # default json when ENVIRONMENT=production
  LOG_LEVEL=INFO

Public API:
  setup_observability(service_name=...)
  get_tracer(name)
  get_meter(name)
  shutdown_observability()
"""
from __future__ import annotations

from .logging_json import configure_logging
from .otel import get_meter, get_tracer, setup_otel, shutdown_otel

_CONFIGURED = False


def setup_observability(*, service_name: str | None = None) -> None:
    """Idempotent process-wide setup. Safe to call from main/api_main/create_app."""
    global _CONFIGURED
    if _CONFIGURED:
        return
    configure_logging()
    setup_otel(service_name=service_name)
    _CONFIGURED = True


def shutdown_observability() -> None:
    shutdown_otel()


__all__ = [
    "setup_observability",
    "shutdown_observability",
    "configure_logging",
    "get_tracer",
    "get_meter",
    "setup_otel",
    "shutdown_otel",
]
