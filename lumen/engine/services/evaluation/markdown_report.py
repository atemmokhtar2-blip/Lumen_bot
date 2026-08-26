"""Human-readable evaluation report for CI / ops."""
from __future__ import annotations

from typing import Any


def render_eval_markdown(summary: dict[str, Any], *, title: str = "Lumen Bot-Bench Report") -> str:
    lines = [
        f"# {title}",
        "",
        f"- **n**: {summary.get('n', 0)}",
        f"- **success_rate**: {summary.get('success_rate', 0)}",
        f"- **avg_attempts**: {summary.get('avg_attempts', 0)}",
        f"- **avg_latency_s**: {summary.get('avg_latency_s', 0)}",
        f"- **avg_cost_usd**: {summary.get('avg_cost_usd', 0)}",
        "",
        "## By platform",
        "",
    ]
    by = summary.get("by_platform") or {}
    if not by:
        lines.append("_no platform breakdown_")
    else:
        lines.append("| platform | n | success_rate |")
        lines.append("|----------|---|--------------|")
        for p, v in sorted(by.items()):
            lines.append(f"| {p} | {v.get('n')} | {v.get('success_rate')} |")
    lines.append("")
    return "\n".join(lines)


__all__ = ["render_eval_markdown"]
