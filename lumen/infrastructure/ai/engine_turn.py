"""AI infrastructure adapter — agent-owned NL turns.

Presentation (Telegram/API) must call this package, not lumen.engine.* directly.
Implementation remains in lumen.engine.services.multi_agent.engine_turn until
the engine is fully relocated under infrastructure.
"""
from __future__ import annotations

from typing import Any

# Re-export result type + entrypoint (zero-copy delegate)
from lumen.engine.services.multi_agent.engine_turn import (  # noqa: F401
    EngineTurnResult,
    handle_user_turn as _impl_handle_user_turn,
)


def handle_user_turn(
    text: str,
    *,
    user_id: int = 0,
    user_data: dict[str, Any] | None = None,
) -> EngineTurnResult:
    """Run one agent-owned NL turn (RouterAgent → tools / generate signal).

    Thin infrastructure boundary: no extra allocation beyond the engine call.
    """
    return _impl_handle_user_turn(text, user_id=user_id, user_data=user_data)


__all__ = ["EngineTurnResult", "handle_user_turn"]
