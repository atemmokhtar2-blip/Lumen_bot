"""Engine UI state — phases, actions, presets, fact-based render."""
from .catalog import UI_ACTIONS, get_action, is_known_action
from .controller import ApplyResult, apply_action, buttons_for_phase, composed_request, missing_for_state
from .models import EngineUiPhase, EngineUiState, RuntimePlaneHint, UiButton, state_summary_ar
from .presets import BOT_TYPE_PRESETS, preset_description, preset_label
from .render import HostRow, UiFacts, render_message

__all__ = [
    "BOT_TYPE_PRESETS",
    "UI_ACTIONS",
    "ApplyResult",
    "EngineUiPhase",
    "EngineUiState",
    "HostRow",
    "RuntimePlaneHint",
    "UiButton",
    "UiFacts",
    "apply_action",
    "buttons_for_phase",
    "composed_request",
    "get_action",
    "is_known_action",
    "missing_for_state",
    "preset_description",
    "preset_label",
    "render_message",
    "state_summary_ar",
]
