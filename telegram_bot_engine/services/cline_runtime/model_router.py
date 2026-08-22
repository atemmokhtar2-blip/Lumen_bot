"""Model provider selection for Cline agent.

Keys never collide:
  GROQ_API_KEY   → Groq (primary engine brain)
  GOOGLE_API_KEY / GEMINI_API_KEY → Gemini
  XAI_API_KEY    → xAI (optional)
  OLLAMA_HOST    → local

CLINE_LLM_PROVIDER / ENGINE_LLM_PROVIDER: groq | gemini | xai | ollama | auto
Default auto order: groq → gemini → xai → ollama
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any


@dataclass
class ModelChoice:
    provider: str  # gemini | xai | groq | ollama | none
    model_id: str
    api_key_env: str
    base_url: str | None = None

    def key_present(self) -> bool:
        if self.provider == "ollama":
            return bool((os.getenv("OLLAMA_HOST") or "").strip())
        if self.provider == "gemini":
            return bool(
                (os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY") or "").strip()
            )
        return bool((os.getenv(self.api_key_env) or "").strip())


def _forced_provider() -> str:
    for name in ("CLINE_LLM_PROVIDER", "ENGINE_LLM_PROVIDER"):
        v = (os.getenv(name) or "").strip().lower()
        if v:
            return v
    return ""


def select_model(*, task: str = "build") -> ModelChoice:
    forced = _forced_provider()
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
        "groq": ModelChoice(
            "groq",
            (os.getenv("GROQ_MODEL") or "qwen/qwen3.6-27b").strip(),
            "GROQ_API_KEY",
            base_url="https://api.groq.com/openai/v1",
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
    # Primary engine: Groq first
    for name in ("groq", "gemini", "xai", "ollama"):
        choice = table[name]
        if choice.key_present():
            return choice
    return ModelChoice("none", "", "")


def describe_runtime() -> dict[str, Any]:
    choice = select_model()
    return {
        "provider": choice.provider,
        "model_id": choice.model_id,
        "key_present": choice.key_present() if choice.provider != "none" else False,
        "base_url": choice.base_url,
        "forced": _forced_provider() or "auto",
    }


__all__ = ["ModelChoice", "describe_runtime", "select_model"]
