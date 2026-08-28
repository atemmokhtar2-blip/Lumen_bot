"""Engine UI state layer (Batch 0) — phases, actions, pure controller."""
from .catalog import UI_ACTIONS, get_action, is_known_action
from .controller import ApplyResult, apply_action, buttons_for_phase, missing_for_state, render_home_message_ar
from .models import EngineUiPhase, EngineUiState, RuntimePlaneHint, UiButton, state_summary_ar

__all__ = [
    "UI_ACTIONS",
    "ApplyResult",
    "EngineUiPhase",
    "EngineUiState",
    "RuntimePlaneHint",
    "UiButton",
    "apply_action",
    "buttons_for_phase",
    "get_action",
    "is_known_action",
    "missing_for_state",
    "render_home_message_ar",
    "state_summary_ar",
]
