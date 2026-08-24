"""Atomic primitives — the Lego bricks of the infinite engine.

No full bot templates here: only triggers, conditions, actions, transformers.
Combinations form novel behaviors via DAG composition.
"""
from __future__ import annotations

from typing import Final

# Re-export from authoritative model so both stay in sync
from ..dynamic_bot_spec import (
    ALLOWED_ACTIONS,
    ALLOWED_CONDITIONS,
    ALLOWED_TRANSFORMERS,
    ALLOWED_TRIGGERS,
    ACTION_ALIASES,
    CONDITION_ALIASES,
    MAX_DAG_DEPTH,
    MAX_NODES,
    normalize_action_type,
    normalize_condition_type,
)

try:
    from ..dynamic_bot_spec import (
        MAX_ACTIONS_PER_NODE,
        MAX_CONDITIONS_PER_NODE,
        MAX_TRANSFORMERS_PER_NODE,
    )
except ImportError:  # pragma: no cover
    MAX_ACTIONS_PER_NODE = 8
    MAX_CONDITIONS_PER_NODE = 8
    MAX_TRANSFORMERS_PER_NODE = 4

__all__ = [
    "ALLOWED_TRIGGERS",
    "ALLOWED_CONDITIONS",
    "ALLOWED_ACTIONS",
    "ALLOWED_TRANSFORMERS",
    "ACTION_ALIASES",
    "CONDITION_ALIASES",
    "MAX_NODES",
    "MAX_ACTIONS_PER_NODE",
    "MAX_CONDITIONS_PER_NODE",
    "MAX_TRANSFORMERS_PER_NODE",
    "MAX_DAG_DEPTH",
    "normalize_action_type",
    "normalize_condition_type",
]
