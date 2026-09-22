"""Clear UI navigation paths — single source of truth.

Tree (parent ← child):
  HOME
  ├─ GEN_TYPE → GEN_SLOTS → GEN_CONFIRM → GENERATING → GEN_DONE → HOST_CONFIRM
  ├─ TEMPLATES → TEMPLATE_DETAIL → TEMPLATE_TRIAL_MINUTES
  │            → TEMPLATE_STATUS
  ├─ DASHBOARD
  ├─ BILLING → PRO_PLAN
  ├─ HELP
  └─ SETTINGS → CONNECTIONS → CONN_GITHUB
              → REFERRAL

Rules
-----
1. Root actions (open_*, home, cancel) reset the stack — path is HOME → screen.
2. Child actions push the phase being left onto slots["_nav"].
3. nav_back pops one step; if stack empty uses PHASE_PARENT.
4. No other module may invent parent links — edit PHASE_PARENT here only.
"""
from __future__ import annotations

from typing import Callable

from .models import EngineUiPhase, EngineUiState

# Explicit parent for every non-HOME phase (cold start / empty stack)
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

# Opening these clears history (destination is a root under HOME)
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

_SLOT_KEY = "_nav"
_MAX_DEPTH = 12


def stack_get(state: EngineUiState) -> list[str]:
    raw = (state.slots.get(_SLOT_KEY) or "").strip()
    return [p for p in raw.split(",") if p] if raw else []


def stack_set(state: EngineUiState, stack: list[str]) -> None:
    stack = [p for p in stack[-_MAX_DEPTH:] if p]
    if stack:
        state.slots[_SLOT_KEY] = ",".join(stack)
    else:
        state.slots.pop(_SLOT_KEY, None)


def stack_clear(state: EngineUiState) -> None:
    state.slots.pop(_SLOT_KEY, None)


def stack_push(state: EngineUiState, leaving: EngineUiPhase) -> None:
    if leaving in {EngineUiPhase.HOME, EngineUiPhase.IDLE}:
        return
    stack = stack_get(state)
    val = leaving.value
    if not stack or stack[-1] != val:
        stack.append(val)
    stack_set(state, stack)


def stack_pop(state: EngineUiState) -> EngineUiPhase | None:
    stack = stack_get(state)
    while stack:
        prev = stack.pop()
        stack_set(state, stack)
        try:
            phase = EngineUiPhase(prev)
        except ValueError:
            continue
        if phase in {EngineUiPhase.HOME, EngineUiPhase.IDLE}:
            continue
        return phase
    return None


def parent_of(phase: EngineUiPhase) -> EngineUiPhase:
    return PHASE_PARENT.get(phase, EngineUiPhase.HOME)


def go_home(state: EngineUiState) -> EngineUiState:
    state.phase = EngineUiPhase.HOME
    state.slots.pop("awaiting_text", None)
    state.slots.pop("billing_expanded", None)
    state.slots.pop("pro_buy_requested", None)
    stack_clear(state)
    state.missing = []
    return state


def go_back(
    state: EngineUiState,
    *,
    refresh_needs: Callable[[EngineUiState], EngineUiState] | None = None,
) -> tuple[EngineUiState, str]:
    """One step back. Prefer stack; fall back to PHASE_PARENT."""
    prev = stack_pop(state)
    if prev is None:
        prev = parent_of(state.phase)
    if prev == state.phase:
        prev = parent_of(prev)
        if prev == state.phase:
            prev = EngineUiPhase.HOME

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
    return state, "رجوع خطوة."


def record_transition(
    *,
    action_id: str,
    previous: EngineUiPhase,
    new_state: EngineUiState,
) -> None:
    """Call once after a successful action mutates phase."""
    if action_id == "nav_back":
        return
    if action_id in ROOT_ACTIONS:
        stack_clear(new_state)
        return
    if new_state.phase != previous:
        stack_push(new_state, previous)
    if action_id == "cancel_generate":
        stack_clear(new_state)


__all__ = [
    "PHASE_PARENT",
    "ROOT_ACTIONS",
    "stack_get",
    "stack_set",
    "stack_clear",
    "stack_push",
    "stack_pop",
    "parent_of",
    "go_home",
    "go_back",
    "record_transition",
]
