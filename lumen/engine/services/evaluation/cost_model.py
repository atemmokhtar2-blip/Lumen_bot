"""Token → USD cost model (production rates via env, defaults are public list prices order-of-magnitude).

Not a mock: uses real token counts from provider usage when present.
"""
from __future__ import annotations

import os
from typing import Any


def _f(name: str, default: float) -> float:
    try:
        return float(os.getenv(name) or default)
    except ValueError:
        return default


def estimate_cost_usd(usage: dict[str, Any] | None = None) -> float:
    """Estimate USD from usage dict.

    Recognized keys: prompt_tokens, completion_tokens, total_tokens,
    prompt_tokens_est, cost_usd (if already set, prefer it).
    """
    u = dict(usage or {})
    if u.get("cost_usd") is not None:
        try:
            return max(0.0, float(u["cost_usd"]))
        except (TypeError, ValueError):
            pass
    # $/1M tokens
    in_rate = _f("LUMEN_COST_INPUT_PER_1M", 0.15)  # e.g. cheap tier default
    out_rate = _f("LUMEN_COST_OUTPUT_PER_1M", 0.60)
    prompt = float(u.get("prompt_tokens") or u.get("prompt_tokens_est") or 0)
    completion = float(u.get("completion_tokens") or 0)
    if prompt == 0 and completion == 0 and u.get("total_tokens"):
        # split unknown total 70/30
        total = float(u["total_tokens"])
        prompt, completion = total * 0.7, total * 0.3
    cost = (prompt / 1_000_000.0) * in_rate + (completion / 1_000_000.0) * out_rate
    return round(max(0.0, cost), 8)


__all__ = ["estimate_cost_usd"]
