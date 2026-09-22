"""UI navigation — one step up the phase tree (no fragile history stack).

Every screen has exactly one parent. ``nav_back`` always goes to that parent.
This is deterministic across workers/restarts (no Redis stack to lose).

Tree
----
HOME
├─ GEN_TYPE → GEN_SLOTS → GEN_CONFIRM → GENERATING → GEN_DONE → HOST_CONFIRM
├─ TEMPLATES → TEMPLATE_DETAIL → TEMPLATE_TRIAL_MINUTES
│            → TEMPLATE_STATUS
├─ DASHBOARD
├─ BILLING → PRO_PLAN
├─ HELP
└─ SETTINGS → CONNECTIONS → CONN_GITHUB
            → REFERRAL
"""
from __future__ import annotations

from typing import Callable

from .models import EngineUiPhase, EngineUiState

PHASE_PARENT: dict[EngineUiPhase, EngineUiPhase] = {
    EngineUiPhase.GEN_TYPE: EngineUiPhase.HOME,
    EngineUiPhase.GEN_SLOTS: EngineUiPhase.GEN_TYPE,
    EngineUiPhase.GEN_CONFIRM: EngineUiPhase.GEN_SLOTS,
    EngineUiPhase.GENERATING: EngineUiPhase.GEN_CONFIRM,
    EngineUiPhase.GEN_DONE: EngineUiPhase.HOME,
    EngineUiPhase.HOST_CONFIRM: EngineUiPhase.GEN_DONE,
    EngineUiPhase.TEMPLATES: EngineUiPhase.HOME,
    EngineUiPhase.TEMPLATE_DETAIL: EngineUiPhase.TEMPLATES,
    EngineUiPhase.TEMPLATE_TRIAL_MINUTES: EngineUiPhase.TEMPLATE_DETAIL,
    EngineUiPhase.TEMPLATE_STATUS: EngineUiPhase.TEMPLATES,
    EngineUiPhase.DASHBOARD: EngineUiPhase.HOME,
    EngineUiPhase.BILLING: EngineUiPhase.HOME,
    EngineUiPhase.PRO_PLAN: EngineUiPhase.BILLING,
    EngineUiPhase.HELP: EngineUiPhase.HOME,
    EngineUiPhase.SETTINGS: EngineUiPhase.HOME,
    EngineUiPhase.REFERRAL: EngineUiPhase.SETTINGS,
    EngineUiPhase.CONNECTIONS: EngineUiPhase.SETTINGS,
    EngineUiPhase.CONN_GITHUB: EngineUiPhase.CONNECTIONS,
    EngineUiPhase.CONTEXT: EngineUiPhase.HOME,
    EngineUiPhase.IDLE: EngineUiPhase.HOME,
}

# Kept for API compatibility; roots no longer need stack clears for back to work.
ROOT_ACTIONS: frozenset[str] = frozenset({
    "home",
    "cancel_generate",
    "open_generate",
    "await_generate_text",
    "open_templates",
    "open_dashboard",
    "open_billing",
    "open_help",
    "open_settings",
})


def parent_of(phase: EngineUiPhase) -> EngineUiPhase:
    return PHASE_PARENT.get(phase, EngineUiPhase.HOME)


def go_home(state: EngineUiState) -> EngineUiState:
    state.phase = EngineUiPhase.HOME
    state.slots.pop("awaiting_text", None)
    state.slots.pop("billing_expanded", None)
    state.slots.pop("pro_buy_requested", None)
    state.slots.pop("_nav", None)  # drop legacy stack if present
    state.slots.pop("_from", None)
    state.missing = []
    return state


def go_back(
    state: EngineUiState,
    *,
    refresh_needs: Callable[[EngineUiState], EngineUiState] | None = None,
) -> tuple[EngineUiState, str]:
    """Exactly one step: current phase → PHASE_PARENT[current]."""
    prev = parent_of(state.phase)
    if prev == state.phase:
        prev = EngineUiPhase.HOME

    # Cleanup when landing
    if prev == EngineUiPhase.GEN_TYPE:
        state.slots["awaiting_text"] = "1"
    elif prev == EngineUiPhase.GEN_SLOTS and refresh_needs is not None:
        state = refresh_needs(state)
    elif prev == EngineUiPhase.BILLING:
        state.slots["billing_expanded"] = "1"
    elif prev == EngineUiPhase.HOME:
        state.slots.pop("awaiting_text", None)
        state.slots.pop("billing_expanded", None)
    elif prev == EngineUiPhase.TEMPLATES:
        state.slots.pop("template_id", None)
        state.slots.pop("template_title", None)

    state.phase = prev
    state.missing = []
    # legacy keys
    state.slots.pop("_nav", None)
    state.slots.pop("_from", None)
    return state, "رجوع خطوة."


def record_transition(
    *,
    action_id: str,
    previous: EngineUiPhase,
    new_state: EngineUiState,
) -> None:
    """No-op for tree-based back (parent map is enough). Clears legacy stack."""
    if action_id in {"home", "cancel_generate", "nav_back"}:
        new_state.slots.pop("_nav", None)
        new_state.slots.pop("_from", None)
        return
    # Drop legacy stack so old sessions do not confuse anything
    if "_nav" in new_state.slots:
        new_state.slots.pop("_nav", None)


# --- legacy aliases (tests / old imports) ---
def stack_clear(state: EngineUiState) -> None:
    state.slots.pop("_nav", None)
    state.slots.pop("_from", None)


def stack_get(state: EngineUiState) -> list[str]:
    return []


def stack_push(state: EngineUiState, leaving: EngineUiPhase) -> None:
    return None


def stack_pop(state: EngineUiState) -> EngineUiPhase | None:
    return None


__all__ = [
    "PHASE_PARENT",
    "ROOT_ACTIONS",
    "parent_of",
    "go_home",
    "go_back",
    "record_transition",
    "stack_clear",
    "stack_get",
    "stack_push",
    "stack_pop",
]
