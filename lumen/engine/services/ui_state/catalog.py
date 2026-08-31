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
        EngineUiPhase.CONTEXT,
    }
)

UI_ACTIONS: dict[str, UiActionSpec] = {
    "home": UiActionSpec("home", "Home", frozenset(EngineUiPhase)),
    "back": UiActionSpec(
        "back",
        "Go back to the logically previous phase",
        frozenset(
            {
                EngineUiPhase.GEN_TYPE,
                EngineUiPhase.GEN_SLOTS,
                EngineUiPhase.GEN_CONFIRM,
                EngineUiPhase.GEN_DONE,
                EngineUiPhase.DASHBOARD,
                EngineUiPhase.BILLING,
                EngineUiPhase.HELP,
                EngineUiPhase.CONTEXT,
            }
        ),
    ),
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
                EngineUiPhase.CONTEXT,
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
        frozenset({EngineUiPhase.GEN_SLOTS, EngineUiPhase.GEN_TYPE, EngineUiPhase.CONTEXT}),
    ),
    "resume_slots": UiActionSpec(
        "resume_slots",
        "Back to engine needs",
        frozenset({EngineUiPhase.GEN_CONFIRM, EngineUiPhase.CONTEXT}),
    ),
    "confirm_generate": UiActionSpec(
        "confirm_generate",
        "Run generation",
        frozenset({EngineUiPhase.GEN_CONFIRM}),
    ),
    "hitl_confirm": UiActionSpec(
        "hitl_confirm",
        "Confirm multi-agent / LangGraph HITL plan",
        frozenset(EngineUiPhase),
    ),
    "hitl_reject": UiActionSpec(
        "hitl_reject",
        "Reject multi-agent / LangGraph HITL plan",
        frozenset(EngineUiPhase),
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
                EngineUiPhase.GEN_DONE,
                EngineUiPhase.DASHBOARD,
                EngineUiPhase.BILLING,
                EngineUiPhase.HELP,
                EngineUiPhase.CONTEXT,
            }
        ),
    ),
    "open_dashboard": UiActionSpec(
        "open_dashboard", "Dashboard",
        _NAV | frozenset({EngineUiPhase.CONTEXT}),
    ),
    "open_billing": UiActionSpec(
        "open_billing", "Billing",
        _NAV | frozenset({EngineUiPhase.CONTEXT}),
    ),
    "open_help": UiActionSpec(
        "open_help", "Help",
        _NAV | frozenset({EngineUiPhase.CONTEXT}),
    ),
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
        frozenset({EngineUiPhase.DASHBOARD, EngineUiPhase.HOME, EngineUiPhase.GEN_DONE, EngineUiPhase.CONTEXT, EngineUiPhase.HOST_CONFIRM}),
    ),
    "dash_stop": UiActionSpec(
        "dash_stop",
        "HostService.stop for instance",
        frozenset({EngineUiPhase.DASHBOARD, EngineUiPhase.HOME, EngineUiPhase.GEN_DONE, EngineUiPhase.CONTEXT, EngineUiPhase.HOST_CONFIRM}),
    ),
    "dash_diagnose": UiActionSpec(
        "dash_diagnose",
        "HostService.diagnose for instance",
        frozenset({EngineUiPhase.DASHBOARD, EngineUiPhase.HOME, EngineUiPhase.GEN_DONE, EngineUiPhase.CONTEXT, EngineUiPhase.HOST_CONFIRM}),
    ),
    "dash_trial": UiActionSpec(
        "dash_trial",
        "Start trial on active project",
        frozenset({EngineUiPhase.DASHBOARD, EngineUiPhase.HOME, EngineUiPhase.GEN_DONE, EngineUiPhase.CONTEXT, EngineUiPhase.HOST_CONFIRM}),
    ),
    "dash_logs": UiActionSpec(
        "dash_logs",
        "HostService.logs for instance",
        frozenset({EngineUiPhase.DASHBOARD, EngineUiPhase.HOME, EngineUiPhase.GEN_DONE, EngineUiPhase.CONTEXT, EngineUiPhase.HOST_CONFIRM}),
    ),
    "retry_generate": UiActionSpec(
        "retry_generate",
        "Retry generation from last description",
        frozenset({EngineUiPhase.CONTEXT, EngineUiPhase.GEN_DONE, EngineUiPhase.GEN_CONFIRM}),
    ),
    "dismiss_event": UiActionSpec(
        "dismiss_event",
        "Clear contextual event → home",
        frozenset({EngineUiPhase.CONTEXT}),
    ),
    "noop": UiActionSpec("noop", "No-op", frozenset(EngineUiPhase)),
    "host_restart": UiActionSpec(
        "host_restart",
        "Re-request bot token and restart HostService instance",
        frozenset({EngineUiPhase.DASHBOARD, EngineUiPhase.HOME, EngineUiPhase.GEN_DONE, EngineUiPhase.CONTEXT}),
    ),
    "ask_gh_token": UiActionSpec(
        "ask_gh_token",
        "Prompt user for GitHub PAT (clone/create)",
        frozenset(EngineUiPhase),
    ),
    "ask_bot_token": UiActionSpec(
        "ask_bot_token",
        "Prompt user for Telegram bot token (host/run)",
        frozenset(EngineUiPhase),
    ),
    "repo_sec": UiActionSpec(
        "repo_sec",
        "Reveal repo understanding section",
        frozenset(EngineUiPhase),
    ),
}





def get_action(action_id: str) -> UiActionSpec | None:
    return UI_ACTIONS.get((action_id or "").strip().lower())


def is_known_action(action_id: str) -> bool:
    return get_action(action_id) is not None
