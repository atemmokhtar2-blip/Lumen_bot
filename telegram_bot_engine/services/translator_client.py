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
    return (os.getenv("MAESTRO_TRANSLATOR_ENABLED") or "0").strip().lower() in {
        "1", "true", "yes", "on",
    }


def translate_request(text: str) -> dict[str, Any] | None:
    """Return a validated translator payload, or None for safe fallback."""
    if not _enabled():
        return None
    base = (os.getenv("MAESTRO_TRANSLATOR_URL") or "").strip().rstrip("/")
    if not base:
        return None
    timeout = float(os.getenv("MAESTRO_TRANSLATOR_TIMEOUT_SEC") or "4")
    try:
        response = requests.post(
            f"{base}/v1/translate",
            json={"text": (text or "")[:20000]},
            timeout=(1.5, timeout),
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
