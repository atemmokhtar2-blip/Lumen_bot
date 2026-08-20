"""Clients for the standalone Qwen spec translator and Gemini chat.

Qwen is the translation path when MAESTRO_TRANSLATOR_URL is configured.
Gemini remains the chat-only path. Any unavailable external service returns
None so the deterministic spec_core fallback remains authoritative.
"""
from __future__ import annotations

import logging
import os
import time
from typing import Any

import requests

logger = logging.getLogger(__name__)


def _enabled() -> bool:
    raw = (os.getenv("MAESTRO_TRANSLATOR_ENABLED") or "").strip().lower()
    if raw in {"0", "false", "no", "off"}:
        return False
    if raw in {"1", "true", "yes", "on"}:
        return True
    return bool((os.getenv("MAESTRO_TRANSLATOR_URL") or "").strip())


def _base_url() -> str:
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


def _headers() -> dict[str, str]:
    token = (os.getenv("MAESTRO_TRANSLATOR_TOKEN") or "").strip()
    if not token:
        return {"Content-Type": "application/json"}
    return {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {token}",
        "X-API-Key": token,
    }


def _timeout() -> tuple[float, float]:
    # Qwen may need to load a 1.5B GGUF on the first request.
    timeout = float(os.getenv("MAESTRO_TRANSLATOR_TIMEOUT_SEC") or "120")
    timeout = max(10.0, min(240.0, timeout))
    return max(5.0, min(15.0, timeout)), timeout


def _retry_count() -> int:
    try:
        return max(0, min(2, int(os.getenv("MAESTRO_TRANSLATOR_RETRY_COUNT") or "1")))
    except ValueError:
        return 1


def _spec_core_capabilities() -> list[str]:
    try:
        from telegram_bot_engine.spec_core.registry import CAPABILITIES
        return sorted(str(key) for key in CAPABILITIES.keys())
    except Exception as exc:
        logger.warning("spec_core capability list unavailable: %s", exc)
        return []


def _gemini_enabled() -> bool:
    try:
        from .gemini_client import enabled as gemini_enabled
        return gemini_enabled()
    except Exception:
        raw = (os.getenv("GEMINI_ENABLED") or "").strip()
        if raw:
            return raw.lower() in {"1", "true", "yes", "on"}
        return bool((os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY") or "").strip())


def translate_request(
    text: str,
    context: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    """Translate a user request to a validated spec_core translation via Qwen."""
    context = context or {}
    if not _enabled():
        return None
    base = _base_url()
    if not base:
        return None
    payload = {
        "text": (text or "")[:20000],
        "conversation_history": list(context.get("conversation_history") or [])[-12:],
        "server_context": dict(context.get("server_facts") or context.get("server_context") or {}),
        "gemini_understanding": dict(context.get("gemini_understanding") or {}),
        "spec_core_capabilities": _spec_core_capabilities(),
    }
    connect_timeout, read_timeout = _timeout()
    last_error: Exception | None = None
    for attempt in range(_retry_count() + 1):
        try:
            response = requests.post(
                f"{base}/v1/translate",
                json=payload,
                headers=_headers(),
                timeout=(connect_timeout, read_timeout),
            )
            if response.status_code in {502, 503, 504} and attempt < _retry_count():
                logger.warning(
                    "Qwen translator returned retryable status=%s attempt=%s/%s",
                    response.status_code,
                    attempt + 1,
                    _retry_count() + 1,
                )
                time.sleep(min(2.0, 0.5 * (attempt + 1)))
                continue
            response.raise_for_status()
            body = response.json()
            translation = body.get("translation") if isinstance(body, dict) else None
            if not isinstance(translation, dict):
                raise ValueError("Qwen response missing translation")
            features = translation.get("features_requested")
            if not isinstance(features, list) or not all(isinstance(x, str) for x in features):
                raise ValueError("Qwen response has invalid features_requested")
            confidence = float(translation.get("confidence") or 0.0)
            minimum = float(os.getenv("MAESTRO_TRANSLATOR_MIN_CONFIDENCE") or "0.60")
            clarification = bool(translation.get("clarification_needed"))
            if not clarification and confidence < minimum:
                raise ValueError(f"Qwen confidence below threshold: {confidence:.2f}")
            if not clarification and not str(translation.get("spec_request") or "").strip():
                raise ValueError("Qwen completed translation has no spec_request")
            logger.info(
                "Qwen translation ok status=%s source=%s model=%s features=%s clarification=%s attempt=%s",
                response.status_code,
                body.get("source") if isinstance(body, dict) else None,
                body.get("model") if isinstance(body, dict) else None,
                features,
                clarification,
                attempt + 1,
            )
            return translation
        except (requests.exceptions.ReadTimeout, requests.exceptions.ConnectTimeout) as exc:
            last_error = exc
            if attempt < _retry_count():
                logger.warning("Qwen translator timeout; retrying attempt=%s/%s", attempt + 1, _retry_count() + 1)
                time.sleep(min(2.0, 0.5 * (attempt + 1)))
                continue
            break
        except requests.exceptions.HTTPError as exc:
            last_error = exc
            break
        except Exception as exc:
            last_error = exc
            break
    logger.warning("Qwen translator unavailable; using deterministic spec_core fallback: %s", last_error)
    return None


def chat_request(message: str, context: dict[str, Any]) -> dict[str, Any] | None:
    """Ask Gemini for chat only; Qwen is intentionally not a chat provider."""
    if not _gemini_enabled():
        logger.warning(
            "Gemini chat skipped; key_present=%s GEMINI_ENABLED=%s",
            bool((os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY") or "").strip()),
            os.getenv("GEMINI_ENABLED"),
        )
        return None
    try:
        from .gemini_client import chat, status_snapshot
        logger.info("Gemini chat path active %s", status_snapshot())
        return chat(message, context or {})
    except Exception as exc:
        logger.exception("Gemini chat unavailable; continuing generation path: %s", exc)
        return None
