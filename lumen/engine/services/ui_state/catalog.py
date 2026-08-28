"""Closed catalog of UI actions (fail closed on unknown)."""
from __future__ import annotations

from dataclasses import dataclass

from .models import EngineUiPhase


@dataclass(frozen=True)
class UiActionSpec:
    action_id: str
    description: str
    allowed_phases: frozenset[EngineUiPhase]


_NAV = frozenset(
    {
        EngineUiPhase.HOME,
        EngineUiPhase.IDLE,
        EngineUiPhase.DASHBOARD,
        EngineUiPhase.BILLING,
        EngineUiPhase.HELP,
        EngineUiPhase.GEN_TYPE,
        EngineUiPhase.GEN_CONFIRM,
        EngineUiPhase.GEN_DONE,
    }
)

UI_ACTIONS: dict[str, UiActionSpec] = {
    "home": UiActionSpec("home", "Home", frozenset(EngineUiPhase)),
    "open_generate": UiActionSpec(
        "open_generate",
        "Open generate type picker",
        frozenset(
            {
                EngineUiPhase.HOME,
                EngineUiPhase.IDLE,
                EngineUiPhase.DASHBOARD,
                EngineUiPhase.GEN_DONE,
                EngineUiPhase.GEN_TYPE,
                EngineUiPhase.GEN_CONFIRM,
            }
        ),
    ),
    "await_generate_text": UiActionSpec(
        "await_generate_text",
        "Await free-text description",
        frozenset({EngineUiPhase.GEN_TYPE, EngineUiPhase.HOME, EngineUiPhase.GEN_CONFIRM}),
    ),
    "pick_type": UiActionSpec(
        "pick_type",
        "Pick bot type preset (arg=shop|notify|tasks|chat|custom)",
        frozenset({EngineUiPhase.GEN_TYPE, EngineUiPhase.GEN_CONFIRM}),
    ),
    "confirm_generate": UiActionSpec(
        "confirm_generate",
        "Confirm and run generation",
        frozenset({EngineUiPhase.GEN_CONFIRM}),
    ),
    "cancel_generate": UiActionSpec(
        "cancel_generate",
        "Cancel guided generate",
        frozenset({EngineUiPhase.GEN_TYPE, EngineUiPhase.GEN_CONFIRM, EngineUiPhase.GENERATING}),
    ),
    "open_dashboard": UiActionSpec("open_dashboard", "Dashboard", _NAV),
    "open_billing": UiActionSpec("open_billing", "Billing/plan", _NAV),
    "open_help": UiActionSpec("open_help", "Help", _NAV),
    "noop": UiActionSpec("noop", "No-op", frozenset(EngineUiPhase)),
}


def get_action(action_id: str) -> UiActionSpec | None:
    return UI_ACTIONS.get((action_id or "").strip().lower())


def is_known_action(action_id: str) -> bool:
    return get_action(action_id) is not None
