"""Concrete adapters: vendor SDKs → TranslateProvider / ChatProvider ports.

Step 1 keeps current production behavior:
  translate → Groq body in translator_client.translate_via_groq
  chat      → Gemini body in translator_client.chat_via_gemini

Step 2: Groq chat is production-ready; Gemini translate adapter is live.
"""
from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


class GroqTranslateAdapter:
    """Production translator (current default)."""

    name = "groq"

    def translate(
        self,
        text: str,
        context: dict[str, Any] | None = None,
    ) -> dict[str, Any] | None:
        from telegram_bot_engine.services.translator_client import translate_via_groq

        return translate_via_groq(text, context)


class GeminiChatAdapter:
    """Production chat (current default)."""

    name = "gemini"

    def chat(
        self,
        message: str,
        context: dict[str, Any] | None = None,
    ) -> dict[str, Any] | None:
        from telegram_bot_engine.services.translator_client import chat_via_gemini

        return chat_via_gemini(message, context)


class GeminiTranslateAdapter:
    """Future default translator — uses gemini_client.translate when enabled."""

    name = "gemini"

    def translate(
        self,
        text: str,
        context: dict[str, Any] | None = None,
    ) -> dict[str, Any] | None:
        try:
            from telegram_bot_engine.services.gemini_client import enabled, translate
        except Exception as exc:
            logger.warning("Gemini translate adapter import failed: %s", exc)
            return None
        if not enabled():
            logger.warning("Gemini translate adapter skipped (disabled / no key)")
            return None
        try:
            return translate(text, context or {})
        except Exception as exc:
            logger.exception("Gemini translate failed: %s", exc)
            return None


class GroqChatAdapter:
    """Production chat (step 2 default) — same JSON contract as Gemini chat."""

    name = "groq"

    def chat(
        self,
        message: str,
        context: dict[str, Any] | None = None,
    ) -> dict[str, Any] | None:
        from telegram_bot_engine.services.llm.groq_chat import chat_via_groq

        return chat_via_groq(message, context)


__all__ = [
    "GroqTranslateAdapter",
    "GeminiChatAdapter",
    "GeminiTranslateAdapter",
    "GroqChatAdapter",
]
