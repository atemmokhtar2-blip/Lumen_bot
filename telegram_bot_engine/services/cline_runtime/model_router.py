"""Model provider selection under Core — Gemini / Grok(xAI) / Ollama.

Does not call models by itself for translation. Used by the general
execution path when a reasoning step is explicitly required.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any


@dataclass
class ModelChoice:
    provider: str  # gemini | xai | ollama | none
    model_id: str
    api_key_env: str
    base_url: str | None = None

    def key_present(self) -> bool:
        if self.provider == "ollama":
            return True
        return bool((os.getenv(self.api_key_env) or "").strip())


def select_model(*, task: str = "build") -> ModelChoice:
    """Prefer explicit ENGINE_LLM_PROVIDER, else first available key."""
    forced = (os.getenv("ENGINE_LLM_PROVIDER") or "").strip().lower()
    table = {
        "gemini": ModelChoice(
            "gemini",
            (os.getenv("GEMINI_MODEL") or "gemini-2.0-flash").strip(),
            "GOOGLE_API_KEY",
        ),
        "google": ModelChoice(
            "gemini",
            (os.getenv("GEMINI_MODEL") or "gemini-2.0-flash").strip(),
            "GOOGLE_API_KEY",
        ),
        "xai": ModelChoice(
            "xai",
            (os.getenv("XAI_MODEL") or "grok-2-latest").strip(),
            "XAI_API_KEY",
        ),
        "grok": ModelChoice(
            "xai",
            (os.getenv("XAI_MODEL") or "grok-2-latest").strip(),
            "XAI_API_KEY",
        ),
        "ollama": ModelChoice(
            "ollama",
            (os.getenv("OLLAMA_MODEL") or "llama3.2").strip(),
            "OLLAMA_HOST",
            base_url=(os.getenv("OLLAMA_HOST") or "http://127.0.0.1:11434").strip(),
        ),
    }
    if forced in table:
        return table[forced]

    # auto: gemini → xai → ollama → none
    for name in ("gemini", "xai", "ollama"):
        choice = table[name]
        if name == "ollama":
            if (os.getenv("OLLAMA_HOST") or "").strip():
                return choice
            continue
        if choice.key_present():
            # Gemini also accepts GEMINI_API_KEY in this codebase
            if name == "gemini":
                if (os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY") or "").strip():
                    return choice
                continue
            return choice
    return ModelChoice("none", "", "")


def describe_runtime() -> dict[str, Any]:
    choice = select_model()
    return {
        "provider": choice.provider,
        "model_id": choice.model_id,
        "key_present": choice.key_present() if choice.provider != "none" else False,
        "base_url": choice.base_url,
    }


__all__ = ["ModelChoice", "describe_runtime", "select_model"]
