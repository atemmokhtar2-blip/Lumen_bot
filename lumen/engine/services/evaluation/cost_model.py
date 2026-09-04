"""Token → USD cost model — model-aware (not flat across all providers).

Uses real token counts from provider usage when present.
Rates are public list-price order-of-magnitude defaults; override via env:

  LUMEN_COST_<PROVIDER>_INPUT_PER_1M
  LUMEN_COST_<PROVIDER>_OUTPUT_PER_1M
  LUMEN_COST_INPUT_PER_1M / LUMEN_COST_OUTPUT_PER_1M  (global fallback)
"""
from __future__ import annotations

import os
import re
from typing import Any


def _f(name: str, default: float) -> float:
    try:
        return float(os.getenv(name) or default)
    except ValueError:
        return default


# USD per 1M tokens — approximate public list prices (order of magnitude).
_DEFAULT_RATES: dict[str, tuple[float, float]] = {
    "deepseek": (0.14, 0.28),
    "gemini": (0.10, 0.40),
    "google": (0.10, 0.40),
    "openai": (0.15, 0.60),
    "anthropic": (0.25, 1.25),
    "groq": (0.05, 0.08),
    "xai": (0.20, 0.50),
    "qwen": (0.20, 0.60),
    "openrouter": (0.20, 0.80),
    "foundry": (0.50, 1.50),
    "azure": (0.50, 1.50),
    "ollama": (0.0, 0.0),
    "llamacpp": (0.0, 0.0),
    "openai_compat": (0.15, 0.60),
    "openai:gpt-4o-mini": (0.15, 0.60),
    "openai:gpt-4o": (2.50, 10.00),
    "openai:o1": (15.0, 60.0),
    "anthropic:claude-3-haiku": (0.25, 1.25),
    "anthropic:claude-3-5-sonnet": (3.0, 15.0),
    "anthropic:claude-sonnet": (3.0, 15.0),
    "gemini:flash-lite": (0.05, 0.20),
    "gemini:flash": (0.10, 0.40),
    "gemini:pro": (1.25, 5.00),
    "deepseek:flash": (0.14, 0.28),
    "deepseek:chat": (0.27, 1.10),
    "deepseek:reasoner": (0.55, 2.19),
    "groq:llama": (0.05, 0.08),
    "xai:grok": (0.20, 0.50),
}


def _norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", (s or "").lower())


def resolve_rates(provider: str = "", model_id: str = "") -> tuple[float, float]:
    """Return (input_usd_per_1m, output_usd_per_1m) for this provider/model."""
    prov = (provider or "").strip().lower() or "openai"
    mid = (model_id or "").strip().lower()

    env_in = os.getenv(f"LUMEN_COST_{prov.upper()}_INPUT_PER_1M")
    env_out = os.getenv(f"LUMEN_COST_{prov.upper()}_OUTPUT_PER_1M")
    if env_in is not None or env_out is not None:
        return (
            float(env_in) if env_in is not None else _f("LUMEN_COST_INPUT_PER_1M", 0.15),
            float(env_out) if env_out is not None else _f("LUMEN_COST_OUTPUT_PER_1M", 0.60),
        )

    mid_n = _norm(mid)
    prov_n = _norm(prov)
    best: tuple[float, float] | None = None
    best_len = -1
    for key, rates in _DEFAULT_RATES.items():
        if ":" not in key:
            continue
        p, m = key.split(":", 1)
        if _norm(p) != prov_n and p not in prov:
            continue
        m_n = _norm(m)
        if m_n and m_n in mid_n and len(m_n) > best_len:
            best = rates
            best_len = len(m_n)
    if best is not None:
        return best

    if prov in _DEFAULT_RATES:
        return _DEFAULT_RATES[prov]

    try:
        from lumen.engine.services.llm.model_catalog import CATALOG

        for m in CATALOG:
            if (m.provider or "").lower() == prov and (
                (m.model_id or "").lower() == mid or (m.id or "").lower() == mid
            ):
                tier = max(1, min(5, int(m.cost_tier or 2)))
                base_in, base_out = 0.10, 0.40
                mult = {1: 0.5, 2: 1.0, 3: 2.5, 4: 8.0, 5: 20.0}[tier]
                return (base_in * mult, base_out * mult)
    except Exception:
        pass

    return (
        _f("LUMEN_COST_INPUT_PER_1M", 0.15),
        _f("LUMEN_COST_OUTPUT_PER_1M", 0.60),
    )


def estimate_cost_usd(usage: dict[str, Any] | None = None) -> float:
    """Estimate USD from usage — model-aware when provider/model_id present."""
    u = dict(usage or {})
    if u.get("cost_usd") is not None:
        try:
            return max(0.0, float(u["cost_usd"]))
        except (TypeError, ValueError):
            pass

    provider = str(u.get("provider") or "")
    model_id = str(u.get("model_id") or u.get("model") or "")
    in_rate, out_rate = resolve_rates(provider, model_id)

    prompt = float(u.get("prompt_tokens") or u.get("prompt_tokens_est") or 0)
    completion = float(u.get("completion_tokens") or 0)
    if prompt == 0 and completion == 0 and u.get("total_tokens"):
        total = float(u["total_tokens"])
        prompt, completion = total * 0.7, total * 0.3

    cost = (prompt / 1_000_000.0) * in_rate + (completion / 1_000_000.0) * out_rate
    return round(max(0.0, cost), 8)


__all__ = ["estimate_cost_usd", "resolve_rates"]
