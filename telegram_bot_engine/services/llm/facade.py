"""LLM facade — single entry for translate/chat; providers are swappable.

Environment (step 2 defaults — speed + quality split):
  TRANSLATE_PROVIDER=gemini|groq   default: gemini
  CHAT_PROVIDER=groq|gemini        default: groq
  Fallbacks: translate gemini→groq, chat groq→gemini

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
    return _env_name(os.getenv("TRANSLATE_PROVIDER"), "gemini")


def get_chat_provider_name() -> str:
    return _env_name(os.getenv("CHAT_PROVIDER"), "groq")


def get_translate_provider() -> TranslateProvider:
    name = get_translate_provider_name()
    cls = _TRANSLATE_REGISTRY.get(name) or GeminiTranslateAdapter
    if name not in _TRANSLATE_REGISTRY:
        logger.warning("Unknown TRANSLATE_PROVIDER=%s; using gemini", name)
    return cls()  # type: ignore[return-value]


def get_chat_provider() -> ChatProvider:
    name = get_chat_provider_name()
    cls = _CHAT_REGISTRY.get(name) or GroqChatAdapter
    if name not in _CHAT_REGISTRY:
        logger.warning("Unknown CHAT_PROVIDER=%s; using groq", name)
    return cls()  # type: ignore[return-value]


def _translate_chain() -> list:
    """Primary + fallback translate providers (deduped)."""
    primary = get_translate_provider()
    chain = [primary]
    # fallback: other vendor
    if getattr(primary, "name", "") == "gemini":
        chain.append(GroqTranslateAdapter())
    else:
        chain.append(GeminiTranslateAdapter())
    seen: set[str] = set()
    out = []
    for p in chain:
        n = getattr(p, "name", "")
        if n in seen:
            continue
        seen.add(n)
        out.append(p)
    return out


def _chat_chain() -> list:
    """Primary + fallback chat providers (deduped)."""
    primary = get_chat_provider()
    chain = [primary]
    if getattr(primary, "name", "") == "groq":
        chain.append(GeminiChatAdapter())
    else:
        chain.append(GroqChatAdapter())
    seen: set[str] = set()
    out = []
    for p in chain:
        n = getattr(p, "name", "")
        if n in seen:
            continue
        seen.add(n)
        out.append(p)
    return out


def translate_request(
    text: str,
    context: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    """Translate user bot request → structured features (provider-agnostic)."""
    last_err: Exception | None = None
    for provider in _translate_chain():
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
            last_err = exc
            logger.warning(
                "translate_request provider=%s failed: %s",
                getattr(provider, "name", "?"),
                exc,
            )
            continue
    if last_err:
        logger.warning("translate_request all providers failed: %s", last_err)
    return None


def chat_request(
    message: str,
    context: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    """Chat reply for Maestro UX (provider-agnostic + fallback)."""
    last_err: Exception | None = None
    for provider in _chat_chain():
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
            last_err = exc
            logger.warning(
                "chat_request provider=%s failed: %s",
                getattr(provider, "name", "?"),
                exc,
            )
            continue
    if last_err:
        logger.warning("chat_request all providers failed: %s", last_err)
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
