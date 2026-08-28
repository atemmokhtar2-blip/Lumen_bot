"""Engine UI state — needs-driven buttons + guided generation."""
from .catalog import UI_ACTIONS, get_action, is_known_action
from .controller import (
    ApplyResult,
    apply_action,
    buttons_for_phase,
    buttons_for_state,
    composed_request,
    missing_for_state,
)
from .engine_needs import EngineNeed, NeedPlan, analyze_needs, remaining_needs
from .models import EngineUiPhase, EngineUiState, RuntimePlaneHint, UiButton, state_summary_ar
from .presets import BOT_TYPE_PRESETS, preset_description, preset_label
from .render import HostRow, UiFacts, render_message
from .ui_events import UiEventKind, apply_event, buttons_for_event, event_label_ar

__all__ = [
    "BOT_TYPE_PRESETS",
    "UI_ACTIONS",
    "ApplyResult",
    "EngineNeed",
    "EngineUiPhase",
    "EngineUiState",
    "HostRow",
    "NeedPlan",
    "RuntimePlaneHint",
    "UiButton",
    "UiFacts",
    "UiEventKind",
    "apply_event",
    "buttons_for_event",
    "event_label_ar",
    "analyze_needs",
    "apply_action",
    "buttons_for_phase",
    "buttons_for_state",
    "composed_request",
    "get_action",
    "is_known_action",
    "missing_for_state",
    "preset_description",
    "preset_label",
    "remaining_needs",
    "render_message",
    "state_summary_ar",
]
