"""Back-compat — authoritative model is spec_core.dynamic_bot_spec."""
from __future__ import annotations

from ..dynamic_bot_spec import (
    Action as ActionAtom,
    Condition as ConditionAtom,
    DynamicBotSpec,
    FlowNode,
    Transformer as TransformerAtom,
    Trigger as TriggerAtom,
    parse_dynamic_spec,
)

__all__ = [
    "TriggerAtom",
    "ConditionAtom",
    "ActionAtom",
    "TransformerAtom",
    "FlowNode",
    "DynamicBotSpec",
    "parse_dynamic_spec",
]
