"""Model-aware LLM cost estimation.

Rates are USD per 1,000,000 tokens (prompt, completion). Unknown hosted
providers use a conservative fallback instead of silently charging zero.
Local Ollama/llama.cpp models are free unless the caller configures otherwise.
"""
from __future__ import annotations

from typing import Any

_MODEL_RATES: tuple[tuple[str, tuple[str, ...], tuple[float, float]], ...] = (
    ("groq", ("llama-3.3", "llama3-3", "llama-3.1"), (0.05, 0.08)),
    ("openai", ("gpt-4o-mini",), (0.15, 0.60)),
    ("anthropic", ("claude-3-5-sonnet", "claude-3.5-sonnet"), (3.00, 15.00)),
    ("deepseek", ("deepseek-v4-flash",), (0.07, 0.28)),
    ("deepseek", ("deepseek-chat", "deepseek-v3"), (0.27, 1.10)),
    ("gemini", ("gemini-3.6-flash", "gemini-2.5-flash"), (0.10, 0.40)),
    ("ollama", ("*",), (0.0, 0.0)),
    ("llamacpp", ("*",), (0.0, 0.0)),
)

_PROVIDER_DEFAULTS: dict[str, tuple[float, float]] = {
    "groq": (0.05, 0.08),
    "openai": (2.50, 10.00),
    "anthropic": (3.00, 15.00),
    "deepseek": (0.27, 1.10),
    "gemini": (0.50, 2.00),
    "google": (0.50, 2.00),
    "openrouter": (3.00, 15.00),
    "foundry": (3.00, 15.00),
    "ollama": (0.0, 0.0),
    "llamacpp": (0.0, 0.0),
}
_UNKNOWN_HOSTED_DEFAULT = (5.00, 20.00)


def _canonical_provider_model(provider: str, model_id: str) -> tuple[str, str]:
    p = str(provider or "").strip().lower().replace("_", "-")
    m = str(model_id or "").strip().lower()
    if p == "openrouter":
        if m.startswith("anthropic/"):
            p, m = "anthropic", m.split("/", 1)[1]
        elif m.startswith("openai/"):
            p, m = "openai", m.split("/", 1)[1]
        elif m.startswith("deepseek/"):
            p, m = "deepseek", m.split("/", 1)[1]
        elif m.startswith("google/"):
            p, m = "gemini", m.split("/", 1)[1]
        elif m.startswith("meta-llama/") or m.startswith("groq/"):
            p, m = "groq", m.split("/", 1)[1]
    if p == "google":
        p = "gemini"
    return p, m


def resolve_rates(provider: str, model_id: str) -> tuple[float, float]:
    """Return (input USD/1M tokens, output USD/1M tokens)."""
    p, m = _canonical_provider_model(provider, model_id)
    for rate_provider, aliases, rates in _MODEL_RATES:
        if p == rate_provider and any(alias == "*" or alias in m for alias in aliases):
            return rates
    return _PROVIDER_DEFAULTS.get(p, _UNKNOWN_HOSTED_DEFAULT)


def estimate_cost_usd(usage: dict[str, Any] | None) -> float:
    """Estimate USD from actual token usage and provider/model identity."""
    data = dict(usage or {})
    provider = str(data.get("provider") or "")
    model_id = str(data.get("model_id") or data.get("model") or "")
    try:
        prompt = max(0, int(data.get("prompt_tokens") or data.get("prompt_tokens_est") or 0))
        completion = max(0, int(data.get("completion_tokens") or 0))
        if prompt == 0 and completion == 0:
            total = max(0, int(data.get("total_tokens") or 0))
            prompt = (total * 7) // 10
            completion = total - prompt
    except (TypeError, ValueError, OverflowError):
        return 0.0
    input_rate, output_rate = resolve_rates(provider, model_id)
    return ((prompt * input_rate) + (completion * output_rate)) / 1_000_000.0
