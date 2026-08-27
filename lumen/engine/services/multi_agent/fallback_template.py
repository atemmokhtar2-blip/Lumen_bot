"""DEAD PATH — verified template fallback is permanently disabled.

Kept as an import-stable module so old callers fail loudly instead of
silently producing a fake bot. Do not re-enable without a real engine.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

_DISABLED_MSG = (
    "verified_template_fallback_disabled: use LangGraph + coding_agent (Cline agent_loop) only"
)


def should_trigger_verified_fallback(*_a: Any, **_k: Any) -> bool:
    """Always False — template fallback is dead."""
    return False


def build_verified_bot(*_a: Any, **_k: Any) -> dict[str, Any]:
    """Refuses to run. Returns explicit failure (never writes a fake bot)."""
    return {
        "ok": False,
        "error": _DISABLED_MSG,
        "engine": "disabled_template_fallback",
        "project_path": None,
    }


def run_verified_fallback_on_state(state: Any, *, work_dir: str | Path | None = None) -> Any:
    """Marks state with explicit refusal — does not generate code."""
    if state is not None and hasattr(state, "extensions"):
        try:
            state.extensions["fallback_template_tried"] = False
            state.extensions["fallback_template_disabled"] = True
            state.extensions["fallback_template_result"] = {
                "ok": False,
                "error": _DISABLED_MSG,
            }
        except Exception:
            pass
    return state


__all__ = [
    "should_trigger_verified_fallback",
    "build_verified_bot",
    "run_verified_fallback_on_state",
]
