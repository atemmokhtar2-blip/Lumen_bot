"""Batch 2 — guided generation UI (types → confirm → engine hint)."""
from __future__ import annotations

from lumen.engine.services.ui_state import (
    EngineUiPhase,
    EngineUiState,
    apply_action,
    composed_request,
    preset_description,
)


def test_pick_shop_goes_confirm_with_description():
    r = apply_action(EngineUiState(phase=EngineUiPhase.HOME), "open_generate")
    assert r.state.phase == EngineUiPhase.GEN_TYPE
    r2 = apply_action(r.state, "pick_type", "shop")
    assert r2.ok
    assert r2.state.phase == EngineUiPhase.GEN_CONFIRM
    assert "متجر" in r2.state.slots.get("bot_description", "") or "سلة" in r2.state.slots.get("bot_description", "")
    assert composed_request(r2.state)


def test_pick_custom_awaits_text():
    st = apply_action(EngineUiState(phase=EngineUiPhase.HOME), "open_generate").state
    r = apply_action(st, "pick_type", "custom")
    assert r.state.phase == EngineUiPhase.GEN_TYPE
    assert r.state.slots.get("awaiting_text") == "1"
    assert "bot_description" in r.state.missing


def test_confirm_sets_run_generation():
    st = apply_action(EngineUiState(phase=EngineUiPhase.HOME), "open_generate").state
    st = apply_action(st, "pick_type", "tasks").state
    r = apply_action(st, "confirm_generate")
    assert r.ok
    assert r.run_generation is True
    assert r.generation_request
    assert r.state.phase == EngineUiPhase.GENERATING


def test_confirm_without_description_fails_soft():
    st = EngineUiState(phase=EngineUiPhase.GEN_CONFIRM, slots={"bot_type": "custom"})
    r = apply_action(st, "confirm_generate")
    assert r.run_generation is False
    assert r.state.phase == EngineUiPhase.GEN_TYPE


def test_cancel_returns_home():
    st = apply_action(EngineUiState(phase=EngineUiPhase.HOME), "open_generate").state
    st = apply_action(st, "pick_type", "chat").state
    r = apply_action(st, "cancel_generate")
    assert r.state.phase == EngineUiPhase.HOME


def test_presets_nonempty():
    for key in ("shop", "notify", "tasks", "chat"):
        assert len(preset_description(key)) > 20
