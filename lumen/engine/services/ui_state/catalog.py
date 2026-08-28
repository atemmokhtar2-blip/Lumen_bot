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
        EngineUiPhase.GEN_SLOTS,
        EngineUiPhase.GEN_CONFIRM,
        EngineUiPhase.GEN_DONE,
    }
)

UI_ACTIONS: dict[str, UiActionSpec] = {
    "home": UiActionSpec("home", "Home", frozenset(EngineUiPhase)),
    "open_generate": UiActionSpec(
        "open_generate",
        "Open generate",
        frozenset(
            {
                EngineUiPhase.HOME,
                EngineUiPhase.IDLE,
                EngineUiPhase.DASHBOARD,
                EngineUiPhase.GEN_DONE,
                EngineUiPhase.GEN_TYPE,
                EngineUiPhase.GEN_CONFIRM,
                EngineUiPhase.GEN_SLOTS,
            }
        ),
    ),
    "await_generate_text": UiActionSpec(
        "await_generate_text",
        "Await free text",
        frozenset({EngineUiPhase.GEN_TYPE, EngineUiPhase.HOME, EngineUiPhase.GEN_CONFIRM, EngineUiPhase.GEN_SLOTS}),
    ),
    "pick_type": UiActionSpec(
        "pick_type",
        "Pick type seed then engine needs",
        frozenset({EngineUiPhase.GEN_TYPE, EngineUiPhase.GEN_CONFIRM}),
    ),
    "fill_slot": UiActionSpec(
        "fill_slot",
        "Fill engine need choice",
        frozenset({EngineUiPhase.GEN_SLOTS, EngineUiPhase.GEN_CONFIRM}),
    ),
    "skip_need": UiActionSpec(
        "skip_need",
        "Skip current engine need",
        frozenset({EngineUiPhase.GEN_SLOTS}),
    ),
    "to_confirm": UiActionSpec(
        "to_confirm",
        "Go confirm with current slots",
        frozenset({EngineUiPhase.GEN_SLOTS, EngineUiPhase.GEN_TYPE}),
    ),
    "resume_slots": UiActionSpec(
        "resume_slots",
        "Back to engine needs",
        frozenset({EngineUiPhase.GEN_CONFIRM}),
    ),
    "confirm_generate": UiActionSpec(
        "confirm_generate",
        "Run generation",
        frozenset({EngineUiPhase.GEN_CONFIRM}),
    ),
    "cancel_generate": UiActionSpec(
        "cancel_generate",
        "Cancel",
        frozenset(
            {
                EngineUiPhase.GEN_TYPE,
                EngineUiPhase.GEN_SLOTS,
                EngineUiPhase.GEN_CONFIRM,
                EngineUiPhase.GENERATING,
            }
        ),
    ),
    "open_dashboard": UiActionSpec("open_dashboard", "Dashboard", _NAV),
    "open_billing": UiActionSpec("open_billing", "Billing", _NAV),
    "open_help": UiActionSpec("open_help", "Help", _NAV),
    "post_trial": UiActionSpec(
        "post_trial",
        "Trial chat plane",
        frozenset({EngineUiPhase.GEN_DONE, EngineUiPhase.DASHBOARD, EngineUiPhase.HOME}),
    ),
    "post_host": UiActionSpec(
        "post_host",
        "Permanent host plane",
        frozenset({EngineUiPhase.GEN_DONE, EngineUiPhase.DASHBOARD, EngineUiPhase.HOME}),
    ),
    "post_zip": UiActionSpec(
        "post_zip",
        "Send ZIP",
        frozenset({EngineUiPhase.GEN_DONE, EngineUiPhase.DASHBOARD}),
    ),
    "post_preview": UiActionSpec(
        "post_preview",
        "Safe preview",
        frozenset({EngineUiPhase.GEN_DONE, EngineUiPhase.DASHBOARD}),
    ),
    "dash_status": UiActionSpec(
        "dash_status",
        "HostService.status for instance",
        frozenset({EngineUiPhase.DASHBOARD}),
    ),
    "dash_stop": UiActionSpec(
        "dash_stop",
        "HostService.stop for instance",
        frozenset({EngineUiPhase.DASHBOARD}),
    ),
    "dash_diagnose": UiActionSpec(
        "dash_diagnose",
        "HostService.diagnose for instance",
        frozenset({EngineUiPhase.DASHBOARD}),
    ),
    "dash_trial": UiActionSpec(
        "dash_trial",
        "Start trial on active project",
        frozenset({EngineUiPhase.DASHBOARD}),
    ),
    "noop": UiActionSpec("noop", "No-op", frozenset(EngineUiPhase)),
}




def get_action(action_id: str) -> UiActionSpec | None:
    return UI_ACTIONS.get((action_id or "").strip().lower())


def is_known_action(action_id: str) -> bool:
    return get_action(action_id) is not None
