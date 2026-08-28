"""Closed catalog of UI actions the engine accepts (fail closed on unknown)."""
from __future__ import annotations

from dataclasses import dataclass

from .models import EngineUiPhase


@dataclass(frozen=True)
class UiActionSpec:
    action_id: str
    description: str
    allowed_phases: frozenset[EngineUiPhase]


UI_ACTIONS: dict[str, UiActionSpec] = {
    "home": UiActionSpec("home", "Home menu", frozenset(EngineUiPhase)),
    "open_generate": UiActionSpec(
        "open_generate",
        "Start generate flow — user must type description",
        frozenset(
            {
                EngineUiPhase.HOME,
                EngineUiPhase.IDLE,
                EngineUiPhase.DASHBOARD,
                EngineUiPhase.GEN_DONE,
                EngineUiPhase.GEN_TYPE,
            }
        ),
    ),
    "await_generate_text": UiActionSpec(
        "await_generate_text",
        "Mark awaiting free-text bot description",
        frozenset({EngineUiPhase.GEN_TYPE, EngineUiPhase.HOME}),
    ),
    "open_dashboard": UiActionSpec(
        "open_dashboard",
        "Dashboard with live host list",
        frozenset(
            {
                EngineUiPhase.HOME,
                EngineUiPhase.IDLE,
                EngineUiPhase.BILLING,
                EngineUiPhase.HELP,
                EngineUiPhase.DASHBOARD,
                EngineUiPhase.GEN_TYPE,
            }
        ),
    ),
    "open_billing": UiActionSpec(
        "open_billing",
        "Live plan facts",
        frozenset(
            {
                EngineUiPhase.HOME,
                EngineUiPhase.IDLE,
                EngineUiPhase.DASHBOARD,
                EngineUiPhase.BILLING,
            }
        ),
    ),
    "open_help": UiActionSpec(
        "open_help",
        "Real capability help text",
        frozenset(
            {
                EngineUiPhase.HOME,
                EngineUiPhase.IDLE,
                EngineUiPhase.DASHBOARD,
                EngineUiPhase.BILLING,
                EngineUiPhase.HELP,
            }
        ),
    ),
    "noop": UiActionSpec("noop", "No-op", frozenset(EngineUiPhase)),
}


def get_action(action_id: str) -> UiActionSpec | None:
    return UI_ACTIONS.get((action_id or "").strip().lower())


def is_known_action(action_id: str) -> bool:
    return get_action(action_id) is not None
