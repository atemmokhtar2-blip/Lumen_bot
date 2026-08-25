"""Strict Sentry integration for the platform and generated bots.

Rules:
  - Disabled unless SENTRY_DSN is set (non-empty).
  - Never raises into caller paths (init failures are logged and ignored).
  - Scrubs Telegram tokens, passwords, Authorization headers, sealed secrets.
  - Optional: SENTRY_ENVIRONMENT, SENTRY_RELEASE, SENTRY_TRACES_SAMPLE_RATE.
"""
from __future__ import annotations

import logging
import os
import re
from typing import Any

logger = logging.getLogger("tbe.sentry")

_TOKEN_RE = re.compile(r"\b\d{6,}:[A-Za-z0-9_-]{20,}\b")
_SECRET_KEY_RE = re.compile(
    r"(?i)(token|password|passwd|secret|authorization|api[_-]?key|bot_token|tbe_token)"
)
_initialized = False


def _dsn() -> str:
    return (os.environ.get("SENTRY_DSN") or os.environ.get("TBE_SENTRY_DSN") or "").strip()


def enabled() -> bool:
    return bool(_dsn())


def _scrub_string(value: str) -> str:
    if not value:
        return value
    value = _TOKEN_RE.sub("[TELEGRAM_TOKEN_REDACTED]", value)
    low = value.lower()
    if any(x in low for x in ("ghp_", "sk-", "xoxb-", "akia")):
        return "[SECRET_REDACTED]"
    return value


def _scrub_obj(obj: Any, depth: int = 0) -> Any:
    if depth > 6:
        return obj
    if isinstance(obj, str):
        return _scrub_string(obj)
    if isinstance(obj, dict):
        out = {}
        for k, v in obj.items():
            ks = str(k)
            if _SECRET_KEY_RE.search(ks):
                out[ks] = "[REDACTED]"
            else:
                out[ks] = _scrub_obj(v, depth + 1)
        return out
    if isinstance(obj, (list, tuple)):
        return type(obj)(_scrub_obj(x, depth + 1) for x in obj)
    return obj


def _before_send(event: dict, hint: dict | None = None) -> dict | None:
    try:
        return _scrub_obj(event)
    except Exception:
        return event


def init_sentry(*, service: str = "lumen", release: str | None = None) -> bool:
    """Initialize Sentry once. Returns True if active."""
    global _initialized
    if _initialized:
        return enabled()
    dsn = _dsn()
    if not dsn:
        logger.info("sentry disabled (no SENTRY_DSN)")
        _initialized = True
        return False
    try:
        import sentry_sdk
        from sentry_sdk.integrations.logging import LoggingIntegration
    except ImportError:
        logger.warning("sentry-sdk not installed; SENTRY_DSN set but inactive")
        _initialized = True
        return False

    env = (os.environ.get("SENTRY_ENVIRONMENT") or os.environ.get("ENVIRONMENT") or "production").strip()
    rel = (release or os.environ.get("SENTRY_RELEASE") or os.environ.get("TBE_RELEASE") or "").strip() or None
    try:
        traces = float(os.environ.get("SENTRY_TRACES_SAMPLE_RATE") or "0.05")
    except Exception:
        traces = 0.05
    traces = max(0.0, min(1.0, traces))

    try:
        sentry_sdk.init(
            dsn=dsn,
            environment=env,
            release=rel,
            traces_sample_rate=traces,
            send_default_pii=False,
            before_send=_before_send,
            integrations=[
                LoggingIntegration(level=logging.ERROR, event_level=logging.ERROR),
            ],
        )
        sentry_sdk.set_tag("service", service)
        node = (os.environ.get("TBE_NODE_ID") or "").strip()
        if node:
            sentry_sdk.set_tag("node_id", node)
        _initialized = True
        logger.info("sentry initialized env=%s service=%s", env, service)
        return True
    except Exception as exc:
        logger.warning("sentry init failed: %s", exc)
        _initialized = True
        return False


def capture_exception(exc: BaseException | None = None, **scope_tags: Any) -> None:
    if not enabled():
        return
    try:
        import sentry_sdk
        with sentry_sdk.push_scope() as scope:
            for k, v in scope_tags.items():
                if v is not None:
                    scope.set_tag(str(k)[:64], str(v)[:200])
            if exc is not None:
                sentry_sdk.capture_exception(exc)
            else:
                sentry_sdk.capture_exception()
    except Exception:
        logger.debug("capture_exception failed", exc_info=True)


def capture_message(message: str, *, level: str = "error", **scope_tags: Any) -> None:
    if not enabled():
        return
    try:
        import sentry_sdk
        with sentry_sdk.push_scope() as scope:
            for k, v in scope_tags.items():
                if v is not None:
                    scope.set_tag(str(k)[:64], str(v)[:200])
            sentry_sdk.capture_message(_scrub_string(message)[:2000], level=level)
    except Exception:
        logger.debug("capture_message failed", exc_info=True)
