"""Structured logging — JSON lines for ELK / Loki / Cloud Logging.

Uses the stdlib logging pipeline (no fragile custom frameworks).
When LOG_FORMAT=json (default in production), every record is one JSON object.
"""
from __future__ import annotations

import json
import logging
import os
import sys
from datetime import datetime, timezone
from typing import Any


class JsonFormatter(logging.Formatter):
    """Single-line JSON log formatter (ECS-ish field names)."""

    RESERVED = {
        "name", "msg", "args", "levelname", "levelno", "pathname", "filename",
        "module", "exc_info", "exc_text", "stack_info", "lineno", "funcName",
        "created", "msecs", "relativeCreated", "thread", "threadName",
        "processName", "process", "message", "asctime",
    }

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "@timestamp": datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "service": os.getenv("OTEL_SERVICE_NAME") or os.getenv("SERVICE_NAME") or "lumen",
            "environment": (os.getenv("ENVIRONMENT") or os.getenv("TBE_ENV") or "production").strip().lower(),
        }
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        # OpenTelemetry trace correlation when present on the record
        for key in ("otelTraceID", "otelSpanID", "trace_id", "span_id"):
            val = getattr(record, key, None)
            if val:
                payload[key] = val
        for k, v in record.__dict__.items():
            if k in self.RESERVED or k.startswith("_"):
                continue
            try:
                json.dumps({k: v})
                payload[k] = v
            except (TypeError, ValueError):
                payload[k] = repr(v)
        return json.dumps(payload, ensure_ascii=False, default=str)


def _want_json() -> bool:
    raw = (os.getenv("LOG_FORMAT") or "").strip().lower()
    if raw in {"json", "structured"}:
        return True
    if raw in {"text", "plain"}:
        return False
    env = (os.getenv("ENVIRONMENT") or os.getenv("TBE_ENV") or "production").strip().lower()
    return env not in {"dev", "development", "local", "test"}


def configure_logging(*, level: str | None = None) -> None:
    """Configure root + lumen loggers. Idempotent-friendly (replaces handlers)."""
    lvl_name = (level or os.getenv("LOG_LEVEL") or "INFO").upper()
    lvl = getattr(logging, lvl_name, logging.INFO)
    root = logging.getLogger()
    root.setLevel(lvl)
    # Remove existing stream handlers to avoid double logs
    for h in list(root.handlers):
        if isinstance(h, logging.StreamHandler):
            root.removeHandler(h)
    handler = logging.StreamHandler(sys.stdout)
    handler.setLevel(lvl)
    if _want_json():
        handler.setFormatter(JsonFormatter())
    else:
        handler.setFormatter(
            logging.Formatter("%(asctime)s | %(levelname)-8s | %(name)s | %(message)s")
        )
    root.addHandler(handler)
    # Quiet noisy libs
    logging.getLogger("asyncio").setLevel(logging.WARNING)
    logging.getLogger("aiohttp.access").setLevel(logging.INFO)
