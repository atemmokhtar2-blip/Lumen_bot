"""Independent engines extracted from the historical spec_core facades."""

from .preset_composer import build_spec, compose_session, detect_stack, session_for_preset
from .preset_scorer import detect_preset, normalize, rank_presets, score_keys, token_hit

__all__ = [
    "build_spec",
    "compose_session",
    "detect_stack",
    "session_for_preset",
    "detect_preset",
    "normalize",
    "rank_presets",
    "score_keys",
    "token_hit",
]
