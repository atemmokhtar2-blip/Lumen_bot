"""Load/save EngineUiState on PTB context.user_data + durable session_store."""
from __future__ import annotations

from typing import Any

from lumen.engine.services.ui_state.models import EngineUiState

_KEY = "engine_ui"


def load_ui_state(user_data: dict[str, Any] | None) -> EngineUiState:
    if not isinstance(user_data, dict):
        return EngineUiState()
    return EngineUiState.from_dict(user_data.get(_KEY) if isinstance(user_data.get(_KEY), dict) else None)


def save_ui_state(user_data: dict[str, Any], state: EngineUiState) -> None:
    user_data[_KEY] = state.to_dict()


def persist_ui_session(user_id: int, user_data: dict[str, Any]) -> None:
    """Persist durable keys (incl. engine_ui) to Redis session store."""
    try:
        from lumen.bot.session_store import get_session_store

        get_session_store().save(int(user_id), dict(user_data))
    except Exception:
        # Never break the message path on session save failure; log at store layer.
        pass
