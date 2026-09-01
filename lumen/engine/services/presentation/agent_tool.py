"""Agent-facing helper: attach a comparison/metrics table intentionally."""
from __future__ import annotations

from typing import Any, Sequence

from .table_policy import (
    TableSpec,
    attach_presentation_table,
    table_from_comparison,
    table_from_explicit,
    table_from_metrics,
)


def agent_present_table(
    state: Any,
    *,
    headers: Sequence[str] | None = None,
    rows: Sequence[Sequence[Any]] | None = None,
    caption: str = "",
    title: str = "",
    kind: str = "custom",
    before: Sequence[Any] | None = None,
    after: Sequence[Any] | None = None,
    labels: Sequence[str] | None = None,
    metrics: dict[str, Any] | None = None,
) -> TableSpec | None:
    """Called by agents/orchestrator when they want a native table.

    Priority: explicit headers/rows → before/after → metrics.
    """
    spec: TableSpec | None = None
    if headers and rows:
        spec = table_from_explicit(
            {
                "headers": list(headers),
                "rows": [list(r) for r in rows],
                "caption": caption,
                "title": title,
                "kind": kind or "custom",
                "reason": "agent explicit present_table",
            }
        )
    if spec is None and before is not None and after is not None:
        spec = table_from_comparison(before, after, labels=labels)
    if spec is None and metrics:
        spec = table_from_metrics(metrics)
    if spec is None:
        return None
    if title:
        spec.title = title[:80]
    if caption:
        spec.caption = caption[:120]
    attach_presentation_table(state, spec)
    return spec


__all__ = ["agent_present_table"]
