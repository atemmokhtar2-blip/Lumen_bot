"""Provider-agnostic contracts for translation and chat.

Business logic (message router, generation bridge, etc.) depends on these
ports only — never on Groq/Gemini client modules directly.
"""
from __future__ import annotations

from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class TranslateProvider(Protocol):
    """Turn a user bot request into a structured spec translation.

    Successful return shape (all keys optional except features discipline):
      purpose: str
      features_requested: list[str]   # registry capability keys only
      flows: list[str]
      strict_spec: bool
      confidence: float
      clarification_needed: bool
      clarification_questions: list[str]
      spec_request: str
      model: str
      rule_features: list[str]        # optional

    Return None when the provider is disabled/unavailable so callers fall
    back to deterministic spec_core / rules.
    """

    name: str

    def translate(
        self,
        text: str,
        context: dict[str, Any] | None = None,
    ) -> dict[str, Any] | None: ...


@runtime_checkable
class ChatProvider(Protocol):
    """Conversational reply for the Lumen Telegram chat path.

    Successful return shape is provider-normalized (see gemini_client._normalize):
      answer: str
      action: dict | None            # e.g. {"name": "generate_bot", ...}
      confidence: float
      ...

    Return None when disabled/unavailable; caller continues without chat AI.
    """

    name: str

    def chat(
        self,
        message: str,
        context: dict[str, Any] | None = None,
    ) -> dict[str, Any] | None: ...


__all__ = ["TranslateProvider", "ChatProvider"]
