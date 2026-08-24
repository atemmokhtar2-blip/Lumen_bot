"""Atomic primitives — the Lego bricks of the infinite engine.

No full bot templates here: only triggers, conditions, actions, transformers.
Combinations form novel behaviors via DAG composition.
"""
from __future__ import annotations

from typing import Final

ALLOWED_TRIGGERS: Final[frozenset[str]] = frozenset({
    "on_message",
    "on_command",
    "on_callback",
    "on_schedule",
    "on_webhook",
    "on_start",
})

ALLOWED_CONDITIONS: Final[frozenset[str]] = frozenset({
    "user_is_admin",
    "user_is_owner",
    "text_contains",
    "text_equals",
    "text_regex",
    "time_between",
    "state_equals",
    "state_exists",
    "always",
})

ALLOWED_ACTIONS: Final[frozenset[str]] = frozenset({
    "send_message",
    "reply_message",
    "update_state",
    "clear_state",
    "call_external_api",
    "log_event",
    "set_command_menu",
    "noop",
})

ALLOWED_TRANSFORMERS: Final[frozenset[str]] = frozenset({
    "extract_regex",
    "to_upper",
    "to_lower",
    "trim",
    "translate_text",
    "summarize",
    "json_pick",
})

# Safety limits (combinatorial explosion control)
MAX_NODES: Final[int] = 15
MAX_ACTIONS_PER_NODE: Final[int] = 8
MAX_CONDITIONS_PER_NODE: Final[int] = 8
MAX_TRANSFORMERS_PER_NODE: Final[int] = 4
MAX_DAG_DEPTH: Final[int] = 15
