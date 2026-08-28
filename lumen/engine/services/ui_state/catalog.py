"""Closed catalog of UI actions the engine accepts (fail closed on unknown)."""
from __future__ import annotations

from dataclasses import dataclass

from .models import EngineUiPhase


@dataclass(frozen=True)
class UiActionSpec:
    action_id: str
    description: str
    # Phases where this action is legal (empty = any known phase in Batch 0 home set)
    allowed_phases: frozenset[EngineUiPhase]


# Batch 0 actions — navigation only, no generation / host / payment side effects.
UI_ACTIONS: dict[str, UiActionSpec] = {
    "home": UiActionSpec(
        "home",
        "Return to home menu",
        frozenset(EngineUiPhase),
    ),
    "open_generate": UiActionSpec(
        "open_generate",
        "Enter generation type phase (Batch 2 will deepen)",
        frozenset({EngineUiPhase.HOME, EngineUiPhase.IDLE, EngineUiPhase.DASHBOARD, EngineUiPhase.GEN_DONE}),
    ),
    "open_dashboard": UiActionSpec(
        "open_dashboard",
        "Open dashboard phase shell",
        frozenset({EngineUiPhase.HOME, EngineUiPhase.IDLE, EngineUiPhase.BILLING, EngineUiPhase.HELP}),
    ),
    "open_billing": UiActionSpec(
        "open_billing",
        "Open billing/plan phase shell",
        frozenset({EngineUiPhase.HOME, EngineUiPhase.IDLE, EngineUiPhase.DASHBOARD}),
    ),
    "open_help": UiActionSpec(
        "open_help",
        "Open help phase shell",
        frozenset({EngineUiPhase.HOME, EngineUiPhase.IDLE, EngineUiPhase.DASHBOARD, EngineUiPhase.BILLING}),
    ),
    "noop": UiActionSpec(
        "noop",
        "No-op (ack only)",
        frozenset(EngineUiPhase),
    ),
}


def get_action(action_id: str) -> UiActionSpec | None:
    return UI_ACTIONS.get((action_id or "").strip().lower())


def is_known_action(action_id: str) -> bool:
    return get_action(action_id) is not None
