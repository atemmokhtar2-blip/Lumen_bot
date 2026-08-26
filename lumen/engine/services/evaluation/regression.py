"""Regression gate: compare current summary against a baseline JSON.

Fails (ok=False) when success_rate drops by more than tolerance or latency spikes.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .eval_store import summarize_evals


def load_baseline(path: str | Path) -> dict[str, Any]:
    p = Path(path)
    if not p.is_file():
        return {}
    return json.loads(p.read_text(encoding="utf-8"))


def save_baseline(summary: dict[str, Any], path: str | Path) -> Path:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    return p


def compare_to_baseline(
    current: dict[str, Any],
    baseline: dict[str, Any],
    *,
    min_success_rate: float = 0.85,
    max_success_drop: float = 0.05,
    max_latency_factor: float = 2.5,
) -> dict[str, Any]:
    cur_sr = float(current.get("success_rate") or 0)
    base_sr = float(baseline.get("success_rate") or cur_sr)
    cur_lat = float(current.get("avg_latency_s") or 0)
    base_lat = float(baseline.get("avg_latency_s") or 0) or 0.0

    issues: list[str] = []
    if cur_sr < min_success_rate:
        issues.append(f"success_rate {cur_sr} < min {min_success_rate}")
    if baseline and (base_sr - cur_sr) > max_success_drop:
        issues.append(f"success_rate drop {base_sr - cur_sr:.4f} > {max_success_drop}")
    if baseline and base_lat > 0 and cur_lat > base_lat * max_latency_factor:
        issues.append(f"latency {cur_lat} > {max_latency_factor}x baseline {base_lat}")

    return {
        "ok": len(issues) == 0,
        "issues": issues,
        "current": current,
        "baseline": baseline,
        "engine": "eval-regression",
    }


def regression_check(
    records: list[dict[str, Any]] | None = None,
    *,
    baseline_path: str | Path | None = None,
) -> dict[str, Any]:
    summary = summarize_evals(records)
    baseline = load_baseline(baseline_path) if baseline_path else {}
    return compare_to_baseline(summary, baseline)


__all__ = ["load_baseline", "save_baseline", "compare_to_baseline", "regression_check"]
