"""LLM facade — single entry for translate/chat; providers are swappable.

Environment (step 1 defaults preserve production behavior):
  TRANSLATE_PROVIDER=groq|gemini   default: groq
  CHAT_PROVIDER=gemini|groq        default: gemini

Callers must use ``translate_request`` / ``chat_request`` from this module
or from ``translator_client`` (re-exports). Do not import Groq/Gemini
clients from routers or generation code.
"""
from __future__ import annotations

import logging
import os
from typing import Any

from .adapters import (
    GeminiChatAdapter,
    GeminiTranslateAdapter,
    GroqChatAdapter,
    GroqTranslateAdapter,
)
from .ports import ChatProvider, TranslateProvider

logger = logging.getLogger(__name__)

_TRANSLATE_REGISTRY: dict[str, type] = {
    "groq": GroqTranslateAdapter,
    "gemini": GeminiTranslateAdapter,
}
_CHAT_REGISTRY: dict[str, type] = {
    "gemini": GeminiChatAdapter,
    "groq": GroqChatAdapter,
}


def _env_name(value: str | None, default: str) -> str:
    raw = (value or "").strip().lower()
    return raw if raw else default


def get_translate_provider_name() -> str:
    return _env_name(os.getenv("TRANSLATE_PROVIDER"), "groq")


def get_chat_provider_name() -> str:
    return _env_name(os.getenv("CHAT_PROVIDER"), "gemini")


def get_translate_provider() -> TranslateProvider:
    name = get_translate_provider_name()
    cls = _TRANSLATE_REGISTRY.get(name) or GroqTranslateAdapter
    if name not in _TRANSLATE_REGISTRY:
        logger.warning("Unknown TRANSLATE_PROVIDER=%s; using groq", name)
    return cls()  # type: ignore[return-value]


def get_chat_provider() -> ChatProvider:
    name = get_chat_provider_name()
    cls = _CHAT_REGISTRY.get(name) or GeminiChatAdapter
    if name not in _CHAT_REGISTRY:
        logger.warning("Unknown CHAT_PROVIDER=%s; using gemini", name)
    return cls()  # type: ignore[return-value]


def translate_request(
    text: str,
    context: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    """Translate user bot request → structured features (provider-agnostic)."""
    provider = get_translate_provider()
    try:
        result = provider.translate(text, context)
        if result is not None:
            logger.info(
                "translate_request provider=%s model=%s features=%s",
                getattr(provider, "name", "?"),
                (result or {}).get("model"),
                (result or {}).get("features_requested"),
            )
        return result
    except Exception as exc:
        logger.exception(
            "translate_request provider=%s failed: %s",
            getattr(provider, "name", "?"),
            exc,
        )
        return None


def chat_request(
    message: str,
    context: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    """Chat reply for Maestro UX (provider-agnostic)."""
    provider = get_chat_provider()
    try:
        result = provider.chat(message, context)
        if result is not None:
            logger.info(
                "chat_request provider=%s keys=%s",
                getattr(provider, "name", "?"),
                list((result or {}).keys())[:8],
            )
        return result
    except Exception as exc:
        logger.exception(
            "chat_request provider=%s failed: %s",
            getattr(provider, "name", "?"),
            exc,
        )
        return None


def status_snapshot() -> dict[str, Any]:
    """Observability: which providers are selected (not whether keys work)."""
    return {
        "translate_provider": get_translate_provider_name(),
        "chat_provider": get_chat_provider_name(),
        "translate_registry": sorted(_TRANSLATE_REGISTRY.keys()),
        "chat_registry": sorted(_CHAT_REGISTRY.keys()),
    }


__all__ = [
    "get_translate_provider",
    "get_chat_provider",
    "get_translate_provider_name",
    "get_chat_provider_name",
    "translate_request",
    "chat_request",
    "status_snapshot",
]
