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
        EngineUiPhase.PRO_PLAN,
        EngineUiPhase.HELP,
        EngineUiPhase.SETTINGS,
        EngineUiPhase.REFERRAL,
        EngineUiPhase.CONNECTIONS,
        EngineUiPhase.CONN_GITHUB,
        EngineUiPhase.GEN_TYPE,
        EngineUiPhase.GEN_SLOTS,
        EngineUiPhase.GEN_CONFIRM,
        EngineUiPhase.GEN_DONE,
        EngineUiPhase.CONTEXT,
    }
)

UI_ACTIONS: dict[str, UiActionSpec] = {
    "home": UiActionSpec("home", "Home", frozenset(EngineUiPhase)),
    "nav_back": UiActionSpec(
        "nav_back",
        "Back one step",
        frozenset(EngineUiPhase),  # allowed everywhere; handler decides destination
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
        frozenset(EngineUiPhase),  # footer on every surface
    ),
    "open_dashboard": UiActionSpec(
        "open_dashboard", "Dashboard",
        _NAV | frozenset({EngineUiPhase.CONTEXT}),
    ),
    "open_billing": UiActionSpec(
        "open_billing", "Billing",
        _NAV | frozenset({EngineUiPhase.CONTEXT}),
    ),
    "show_more_plans": UiActionSpec(
        "show_more_plans",
        "Reveal Pro plan button on Billing",
        frozenset({EngineUiPhase.BILLING}),
    ),
    "view_pro_plan": UiActionSpec(
        "view_pro_plan",
        "Open Lumen Pro plan details",
        frozenset({EngineUiPhase.BILLING, EngineUiPhase.PRO_PLAN, EngineUiPhase.CONTEXT}),
    ),
    "buy_pro_plan": UiActionSpec(
        "buy_pro_plan",
        "Send Telegram Stars invoice for Lumen Pro",
        frozenset({EngineUiPhase.PRO_PLAN, EngineUiPhase.CONTEXT}),
    ),
    "open_help": UiActionSpec(
        "open_help", "Help",
        _NAV | frozenset({EngineUiPhase.CONTEXT}),
    ),
    "open_settings": UiActionSpec(
        "open_settings",
        "Settings",
        frozenset(
            {
                EngineUiPhase.HOME,
                EngineUiPhase.IDLE,
                EngineUiPhase.DASHBOARD,
                EngineUiPhase.BILLING,
                EngineUiPhase.HELP,
                EngineUiPhase.SETTINGS,
                EngineUiPhase.REFERRAL,
                EngineUiPhase.CONNECTIONS,
                EngineUiPhase.CONN_GITHUB,
                EngineUiPhase.CONTEXT,
            }
        ),
    ),
    "open_referral": UiActionSpec(
        "open_referral",
        "Referral program",
        frozenset(
            {
                EngineUiPhase.HOME,
                EngineUiPhase.IDLE,
                EngineUiPhase.SETTINGS,
                EngineUiPhase.REFERRAL,
                EngineUiPhase.BILLING,
                EngineUiPhase.HELP,
                EngineUiPhase.CONNECTIONS,
                EngineUiPhase.CONTEXT,
            }
        ),
    ),
    "open_connections": UiActionSpec(
        "open_connections",
        "Connections hub",
        frozenset(
            {
                EngineUiPhase.SETTINGS,
                EngineUiPhase.CONNECTIONS,
                EngineUiPhase.CONN_GITHUB,
                EngineUiPhase.HOME,
                EngineUiPhase.IDLE,
            }
        ),
    ),

    "open_templates": UiActionSpec(
        "open_templates",
        "Templates gallery",
        frozenset({
            EngineUiPhase.HOME,
            EngineUiPhase.IDLE,
            EngineUiPhase.TEMPLATES,
            EngineUiPhase.TEMPLATE_DETAIL,
            EngineUiPhase.TEMPLATE_TRIAL_MINUTES,
            EngineUiPhase.TEMPLATE_STATUS,
            EngineUiPhase.DASHBOARD,
        }),
    ),
    "tpl_select": UiActionSpec(
        "tpl_select",
        "Select template",
        frozenset({EngineUiPhase.TEMPLATES, EngineUiPhase.TEMPLATE_DETAIL}),
    ),
    "tpl_trial": UiActionSpec(
        "tpl_trial",
        "Template trial",
        frozenset({EngineUiPhase.TEMPLATE_DETAIL, EngineUiPhase.TEMPLATE_TRIAL_MINUTES}),
    ),
    "tpl_minutes": UiActionSpec(
        "tpl_minutes",
        "Template trial minutes",
        frozenset({EngineUiPhase.TEMPLATE_TRIAL_MINUTES, EngineUiPhase.TEMPLATE_DETAIL}),
    ),
    "tpl_permanent": UiActionSpec(
        "tpl_permanent",
        "Template permanent",
        frozenset({EngineUiPhase.TEMPLATE_DETAIL}),
    ),

    "tpl_mine": UiActionSpec(
        "tpl_mine",
        "My template bots",
        frozenset({
            EngineUiPhase.TEMPLATES,
            EngineUiPhase.TEMPLATE_DETAIL,
            EngineUiPhase.TEMPLATE_STATUS,
            EngineUiPhase.HOME,
        }),
    ),
    "tpl_stop": UiActionSpec(
        "tpl_stop",
        "Stop template instance",
        frozenset({EngineUiPhase.TEMPLATE_STATUS}),
    ),
    "tpl_refresh_mine": UiActionSpec(
        "tpl_refresh_mine",
        "Refresh my templates",
        frozenset({EngineUiPhase.TEMPLATE_STATUS}),
    ),
    "conn_github": UiActionSpec(
        "conn_github",
        "Open GitHub connection / repos",
        frozenset(
            {
                EngineUiPhase.CONNECTIONS,
                EngineUiPhase.CONN_GITHUB,
                EngineUiPhase.SETTINGS,
            }
        ),
    ),
    "conn_gh_connect": UiActionSpec(
        "conn_gh_connect",
        "Start GitHub App install (or PAT fallback)",
        frozenset(
            {
                EngineUiPhase.CONNECTIONS,
                EngineUiPhase.CONN_GITHUB,
                EngineUiPhase.SETTINGS,
            }
        ),
    ),
    "conn_gh_pat": UiActionSpec(
        "conn_gh_pat",
        "Manual GitHub PAT connect (advanced)",
        frozenset(
            {
                EngineUiPhase.CONNECTIONS,
                EngineUiPhase.CONN_GITHUB,
                EngineUiPhase.SETTINGS,
            }
        ),
    ),
    "conn_gh_disconnect": UiActionSpec(
        "conn_gh_disconnect",
        "Disconnect GitHub and delete stored credentials",
        frozenset(
            {
                EngineUiPhase.CONNECTIONS,
                EngineUiPhase.CONN_GITHUB,
                EngineUiPhase.SETTINGS,
            }
        ),
    ),
    "conn_gh_disconnect_confirm": UiActionSpec(
        "conn_gh_disconnect_confirm",
        "Confirm permanent GitHub disconnect",
        frozenset(
            {
                EngineUiPhase.CONNECTIONS,
                EngineUiPhase.CONN_GITHUB,
                EngineUiPhase.SETTINGS,
            }
        ),
    ),
    "conn_gh_activity": UiActionSpec(
        "conn_gh_activity",
        "Show GitHub connection activity log",
        frozenset(
            {
                EngineUiPhase.CONNECTIONS,
                EngineUiPhase.CONN_GITHUB,
                EngineUiPhase.SETTINGS,
            }
        ),
    ),
    "gh_confirm_push": UiActionSpec(
        "gh_confirm_push",
        "Confirm pending git push",
        frozenset(
            {
                EngineUiPhase.CONN_GITHUB,
                EngineUiPhase.DASHBOARD,
                EngineUiPhase.HOME,
                EngineUiPhase.GEN_DONE,
            }
        ),
    ),
    "gh_cancel_push": UiActionSpec(
        "gh_cancel_push",
        "Cancel pending git push",
        frozenset(
            {
                EngineUiPhase.CONN_GITHUB,
                EngineUiPhase.DASHBOARD,
                EngineUiPhase.HOME,
                EngineUiPhase.GEN_DONE,
            }
        ),
    ),
    "conn_gh_refresh": UiActionSpec(
        "conn_gh_refresh",
        "Refresh GitHub repo list",
        frozenset({EngineUiPhase.CONN_GITHUB}),
    ),
    "conn_gh_page": UiActionSpec(
        "conn_gh_page",
        "Paginate GitHub repos",
        frozenset({EngineUiPhase.CONN_GITHUB}),
    ),
    "conn_gh_select": UiActionSpec(
        "conn_gh_select",
        "Select a GitHub repository",
        frozenset({EngineUiPhase.CONN_GITHUB}),
    ),
    "post_trial": UiActionSpec(
        "post_trial",
        "Trial chat plane",
        frozenset({EngineUiPhase.GEN_DONE, EngineUiPhase.DASHBOARD, EngineUiPhase.HOME, EngineUiPhase.CONN_GITHUB}),
    ),
    "post_host": UiActionSpec(
        "post_host",
        "Permanent host plane",
        frozenset({EngineUiPhase.GEN_DONE, EngineUiPhase.DASHBOARD, EngineUiPhase.HOME, EngineUiPhase.CONN_GITHUB}),
    ),
    "post_open_url": UiActionSpec(
        "post_open_url",
        "Open public URL",
        frozenset({EngineUiPhase.GEN_DONE, EngineUiPhase.DASHBOARD, EngineUiPhase.HOME, EngineUiPhase.CONTEXT}),
    ),
    "post_logs": UiActionSpec(
        "post_logs",
        "Project logs",
        frozenset({EngineUiPhase.GEN_DONE, EngineUiPhase.DASHBOARD, EngineUiPhase.HOME, EngineUiPhase.CONTEXT}),
    ),
    "post_stop": UiActionSpec(
        "post_stop",
        "Stop hosted project",
        frozenset({EngineUiPhase.GEN_DONE, EngineUiPhase.DASHBOARD, EngineUiPhase.HOME, EngineUiPhase.CONTEXT}),
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
    "dash_backup": UiActionSpec(
        "dash_backup",
        "Backup project data via hosting.backup_manager",
        frozenset({EngineUiPhase.DASHBOARD, EngineUiPhase.HOME, EngineUiPhase.GEN_DONE, EngineUiPhase.CONTEXT, EngineUiPhase.HOST_CONFIRM}),
    ),
    "dash_versions": UiActionSpec(
        "dash_versions",
        "List deploy versions for hosted project",
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
