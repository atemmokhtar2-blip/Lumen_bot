"""Presentation policies — how engine/agent results are shown to users."""
from .table_policy import (
    TableSpec,
    attach_presentation_table,
    decide_and_attach,
    decide_table_for_state,
    should_use_table,
    table_from_comparison,
    table_from_explicit,
    table_from_findings,
    table_from_metrics,
    table_from_stages,
)

__all__ = [
    "TableSpec",
    "should_use_table",
    "table_from_explicit",
    "table_from_comparison",
    "table_from_stages",
    "table_from_findings",
    "table_from_metrics",
    "decide_table_for_state",
    "attach_presentation_table",
    "decide_and_attach",
]
