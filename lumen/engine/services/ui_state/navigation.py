"""UI navigation — one-step back with destination in the button itself.

``nav_back`` embeds a short parent-phase code in callback arg (≤6 chars).
Telegram signed callbacks truncate args to 12 bytes; long phase names like
``template_detail`` were corrupted. Short codes fix that permanently.

Fallback when arg missing: PHASE_PARENT[current].
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

# Short codes for signed callback arg (must stay ≤12 after encode)
_PHASE_CODE: dict[EngineUiPhase, str] = {
    EngineUiPhase.HOME: "home",
    EngineUiPhase.IDLE: "idle",
    EngineUiPhase.GEN_TYPE: "gent",
    EngineUiPhase.GEN_SLOTS: "gens",
    EngineUiPhase.GEN_CONFIRM: "genc",
    EngineUiPhase.GENERATING: "genr",
    EngineUiPhase.GEN_DONE: "gend",
    EngineUiPhase.HOST_CONFIRM: "host",
    EngineUiPhase.TEMPLATES: "tpls",
    EngineUiPhase.TEMPLATE_DETAIL: "tpld",
    EngineUiPhase.TEMPLATE_TRIAL_MINUTES: "tplm",
    EngineUiPhase.TEMPLATE_STATUS: "tplst",
    EngineUiPhase.DASHBOARD: "dash",
    EngineUiPhase.BILLING: "bill",
    EngineUiPhase.PRO_PLAN: "pro",
    EngineUiPhase.HELP: "help",
    EngineUiPhase.SETTINGS: "set",
    EngineUiPhase.REFERRAL: "ref",
    EngineUiPhase.CONNECTIONS: "conn",
    EngineUiPhase.CONN_GITHUB: "gh",
    EngineUiPhase.CONTEXT: "ctx",
}
_CODE_PHASE: dict[str, EngineUiPhase] = {v: k for k, v in _PHASE_CODE.items()}
# also accept full phase.value
for _p in EngineUiPhase:
    _CODE_PHASE.setdefault(_p.value, _p)

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


def phase_code(phase: EngineUiPhase) -> str:
    return _PHASE_CODE.get(phase, "home")


def phase_from_code(code: str) -> EngineUiPhase | None:
    raw = (code or "").strip().lower()
    if not raw:
        return None
    return _CODE_PHASE.get(raw)


def resolve_back_target(current: EngineUiPhase, arg: str = "") -> EngineUiPhase:
    target = phase_from_code(arg)
    if target is not None and target != current:
        return target
    prev = parent_of(current)
    return EngineUiPhase.HOME if prev == current else prev


def go_home(state: EngineUiState) -> EngineUiState:
    state.phase = EngineUiPhase.HOME
    state.slots.pop("awaiting_text", None)
    state.slots.pop("billing_expanded", None)
    state.slots.pop("pro_buy_requested", None)
    state.slots.pop("_nav", None)
    state.slots.pop("_from", None)
    state.missing = []
    return state


def go_back(
    state: EngineUiState,
    *,
    arg: str = "",
    refresh_needs: Callable[[EngineUiState], EngineUiState] | None = None,
) -> tuple[EngineUiState, str]:
    prev = resolve_back_target(state.phase, arg)

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
    state.slots.pop("_nav", None)
    state.slots.pop("_from", None)
    return state, "رجوع خطوة."


def record_transition(
    *,
    action_id: str,
    previous: EngineUiPhase,
    new_state: EngineUiState,
) -> None:
    new_state.slots.pop("_nav", None)
    new_state.slots.pop("_from", None)


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
    "phase_code",
    "phase_from_code",
    "resolve_back_target",
    "go_home",
    "go_back",
    "record_transition",
    "stack_clear",
    "stack_get",
    "stack_push",
    "stack_pop",
]
