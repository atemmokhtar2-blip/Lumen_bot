"""Preset composition engine.

Composition is exposed as a separate boundary while ``spec_core.presets``
continues to provide the historical API consumed by existing callers.
"""
from __future__ import annotations


def compose_session(
    presets: list[str],
    *,
    user_id: int = 0,
    bot_name: str = "",
    request: str = "",
):
    from .. import presets as legacy
    return legacy.compose_session(
        presets,
        user_id=user_id,
        bot_name=bot_name,
        request=request,
    )


def detect_stack(request: str, *, limit: int = 8) -> list[str]:
    from .. import presets as legacy
    return legacy.detect_preset_stack(request, limit=limit)


def session_for_preset(preset: str, *, user_id: int = 0, bot_name: str = ""):
    from .. import presets as legacy
    return legacy.session_for_preset(preset, user_id=user_id, bot_name=bot_name)


def build_spec(request: str, *, user_id: int = 0):
    from .. import presets as legacy
    return legacy.spec_from_request(request, user_id=user_id)


__all__ = ["compose_session", "detect_stack", "session_for_preset", "build_spec"]
