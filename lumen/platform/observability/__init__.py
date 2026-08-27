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
    _setup_langsmith(service_name=service_name)
    _CONFIGURED = True


def _setup_langsmith(*, service_name: str | None = None) -> None:
    """Enable LangSmith / LangChain tracing when API key present (LangGraph-compatible)."""
    import os
    import logging
    log = logging.getLogger(__name__)
    key = (os.getenv("LANGCHAIN_API_KEY") or os.getenv("LANGSMITH_API_KEY") or "").strip()
    if not key:
        return
    os.environ.setdefault("LANGCHAIN_TRACING_V2", "true")
    os.environ.setdefault("LANGCHAIN_API_KEY", key)
    if service_name:
        os.environ.setdefault("LANGCHAIN_PROJECT", service_name)
    # Optional Phoenix OTEL exporter when PHOENIX_COLLECTOR_ENDPOINT is set
    phoenix = (os.getenv("PHOENIX_COLLECTOR_ENDPOINT") or "").strip()
    if phoenix:
        try:
            from openinference.instrumentation.langchain import LangChainInstrumentor  # type: ignore
            LangChainInstrumentor().instrument()
            log.info("phoenix langchain instrumentation enabled")
        except Exception:
            log.debug("phoenix instrumentation unavailable", exc_info=True)
    log.info("langsmith tracing enabled project=%s", os.getenv("LANGCHAIN_PROJECT"))


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
