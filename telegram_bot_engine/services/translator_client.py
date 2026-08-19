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


def _base_url() -> str:
    """Normalize a Railway variable copied with an endpoint suffix."""
    base = (os.getenv("MAESTRO_TRANSLATOR_URL") or "").strip().rstrip("/")
    suffixes = (
        "/health/v1/chat",
        "/v1/chat",
        "/health/v1",
        "/health",
        "/v1",
    )
    changed = True
    while changed:
        changed = False
        for suffix in suffixes:
            if base.endswith(suffix):
                base = base[: -len(suffix)].rstrip("/")
                changed = True
                break
    return base


def _gemini_enabled() -> bool:
    raw = os.getenv("GEMINI_ENABLED")
    if raw is not None:
        return raw.strip().lower() in {"1", "true", "yes", "on"}
    return bool((os.getenv("GEMINI_API_KEY") or "").strip())


def translate_request(
    text: str,
    context: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    """Return a validated translator payload, or None for safe fallback."""
    if _gemini_enabled():
        try:
            from .gemini_client import translate
            result = translate(text, context or {})
            payload = result.get("translation") if isinstance(result, dict) else None
            if isinstance(payload, dict):
                return payload
        except Exception as exc:
            logger.warning("Gemini translation unavailable; using existing fallback: %s", exc)
        return None
    if not _enabled():
        return None
    base = _base_url()
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
    """Ask Gemini or the legacy standalone layer using server-built context."""
    if _gemini_enabled():
        try:
            from .gemini_client import chat
            return chat(message, context or {})
        except Exception as exc:
            logger.exception("Gemini chat unavailable; continuing generation path: %s", exc)
        return None
    if not _enabled():
        return None
    base = _base_url()
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
        logger.info(
            "standalone chat response status=%s ok=%s answered=%s source=%s answer_len=%s",
            response.status_code,
            body.get("ok") if isinstance(body, dict) else None,
            body.get("answered") if isinstance(body, dict) else None,
            body.get("source") if isinstance(body, dict) else None,
            len(str(body.get("answer") or "")) if isinstance(body, dict) else 0,
        )
        if not isinstance(body, dict) or not body.get("ok"):
            return None
        if not isinstance(body.get("answer"), str) or not body["answer"].strip():
            return None
        return body
    except Exception as exc:
        logger.exception("standalone chat unavailable; continuing generation path: %s", exc)
        return None
