"""Engine UI state layer — phases, actions, pure controller, fact-based render."""
from .catalog import UI_ACTIONS, get_action, is_known_action
from .controller import ApplyResult, apply_action, buttons_for_phase, missing_for_state
from .models import EngineUiPhase, EngineUiState, RuntimePlaneHint, UiButton, state_summary_ar
from .render import HostRow, UiFacts, render_message

__all__ = [
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
    "get_action",
    "is_known_action",
    "missing_for_state",
    "render_message",
    "state_summary_ar",
]
