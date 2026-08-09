"""Multi-provider chat router for planning and codegen.

Order (overridable via AI_PROVIDER_ORDER):
  1. openai  (ChatGPT) — best for complex structured plans/code
  2. hf      (Hugging Face)
  3. groq    (fallback)

Never hardcodes tokens. Reads from environment only.
"""
from __future__ import annotations

import logging
import os
from typing import Any

logger = logging.getLogger(__name__)

_DEFAULT_ORDER = ("openai", "hf", "groq")


def _order() -> tuple[str, ...]:
    raw = (os.environ.get("AI_PROVIDER_ORDER") or "").strip()
    if not raw:
        return _DEFAULT_ORDER
    parts = tuple(x.strip().lower() for x in raw.split(",") if x.strip())
    return parts or _DEFAULT_ORDER


def _load(name: str):
    if name in ("openai", "chatgpt", "gpt"):
        from . import openai_provider as mod
        return "openai", mod
    if name in ("hf", "huggingface", "hugging_face"):
        from . import hf_provider as mod
        return "hf", mod
    if name in ("groq",):
        from . import groq_provider as mod
        return "groq", mod
    return name, None


def any_enabled() -> bool:
    for name in _order():
        _, mod = _load(name)
        if mod is not None and mod.enabled():
            return True
    return False


def enabled_providers() -> list[str]:
    out: list[str] = []
    for name in _order():
        label, mod = _load(name)
        if mod is not None and mod.enabled():
            out.append(label)
    return out


def chat(
    messages: list[dict[str, Any]],
    *,
    timeout: int = 120,
    max_tokens: int = 4096,
    temperature: float = 0.0,
    json_mode: bool = False,
    model: str | None = None,
) -> tuple[str, str]:
    """Try providers in order. Return (content, provider:model)."""
    errors: list[str] = []
    for name in _order():
        label, mod = _load(name)
        if mod is None:
            continue
        if not mod.enabled():
            continue
        try:
            text, used = mod.chat(
                messages,
                timeout=timeout,
                max_tokens=max_tokens,
                temperature=temperature,
                json_mode=json_mode,
                model=model,
            )
            if text:
                tag = used if ":" in str(used) else f"{label}:{used}"
                return text, tag
            errors.append(f"{label}:empty")
        except Exception as exc:
            errors.append(f"{label}:{type(exc).__name__}:{exc}"[:400])
            logger.warning("provider %s failed: %s", label, exc)
    if not errors:
        raise RuntimeError(
            "No AI provider configured. Set OPENAI_API_KEY and/or HF_TOKEN "
            "(and optionally GROQ_API_KEY)."
        )
    raise RuntimeError("; ".join(errors)[:1200])


def healthcheck(*, timeout: int = 30) -> dict[str, Any]:
    results: dict[str, Any] = {}
    for name in _order():
        label, mod = _load(name)
        if mod is None:
            continue
        try:
            results[label] = mod.healthcheck(timeout=timeout)
        except Exception as exc:
            results[label] = {"ok": False, "error": str(exc)[:300], "enabled": False}
    return {
        "any_ok": any(bool(v.get("ok")) for v in results.values()),
        "providers": results,
        "order": list(_order()),
    }


__all__ = ["any_enabled", "enabled_providers", "chat", "healthcheck"]
