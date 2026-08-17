"""Optional client for the standalone Maestro translator service.

Disabled by default. When unavailable, callers must continue through the
existing deterministic spec_core path without changing its behavior.
"""
from __future__ import annotations

import logging
import os
from typing import Any

import requests

logger = logging.getLogger(__name__)


def _enabled() -> bool:
    """Enable when explicitly requested, or when a translator URL is configured.

    The URL is still required below, so an incomplete deployment remains a safe
    no-op. This avoids silently falling back when Railway has only the URL set.
    """
    raw = (os.getenv("MAESTRO_TRANSLATOR_ENABLED") or "").strip().lower()
    if raw in {"0", "false", "no", "off"}:
        return False
    if raw in {"1", "true", "yes", "on"}:
        return True
    return bool((os.getenv("MAESTRO_TRANSLATOR_URL") or "").strip())


def translate_request(text: str) -> dict[str, Any] | None:
    """Return a validated translator payload, or None for safe fallback."""
    if not _enabled():
        return None
    base = (os.getenv("MAESTRO_TRANSLATOR_URL") or "").strip().rstrip("/")
    if not base:
        return None
    timeout = float(os.getenv("MAESTRO_TRANSLATOR_TIMEOUT_SEC") or "4")
    connect_timeout = max(3.0, min(10.0, timeout))
    try:
        response = requests.post(
            f"{base}/v1/translate",
            json={"text": (text or "")[:20000]},
            timeout=(connect_timeout, timeout),
        )
        response.raise_for_status()
        body = response.json()
        translation = body.get("translation") if isinstance(body, dict) else None
        if not isinstance(translation, dict):
            return None
        features = translation.get("features_requested")
        if not isinstance(features, list) or not all(isinstance(x, str) for x in features):
            return None
        confidence = float(translation.get("confidence") or 0.0)
        if confidence < float(os.getenv("MAESTRO_TRANSLATOR_MIN_CONFIDENCE") or "0.60"):
            return None
        return translation
    except Exception as exc:
        logger.warning("standalone translator unavailable; using spec_core fallback: %s", exc)
        return None


def chat_request(message: str, context: dict[str, Any]) -> dict[str, Any] | None:
    """Ask the standalone conversational layer using server-built user context."""
    if not _enabled():
        return None
    base = (os.getenv("MAESTRO_TRANSLATOR_URL") or "").strip().rstrip("/")
    if not base:
        return None
    timeout = float(os.getenv("MAESTRO_TRANSLATOR_TIMEOUT_SEC") or "4")
    connect_timeout = max(3.0, min(10.0, timeout))
    try:
        response = requests.post(
            f"{base}/v1/chat",
            json={"message": (message or "")[:20000], "context": context or {}},
            timeout=(connect_timeout, timeout),
        )
        response.raise_for_status()
        body = response.json()
        if not isinstance(body, dict) or not body.get("ok"):
            return None
        if not isinstance(body.get("answer"), str) or not body["answer"].strip():
            return None
        return body
    except Exception as exc:
        logger.warning("standalone chat unavailable; continuing generation path: %s", exc)
        return None
