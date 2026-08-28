"""Batch 6 — contextual events and smart buttons."""
from __future__ import annotations

from lumen.engine.services.ui_state import (
    EngineUiPhase,
    EngineUiState,
    UiEventKind,
    apply_action,
    apply_event,
    buttons_for_event,
    buttons_for_state,
)


def test_generation_failed_buttons():
    actions = [b.action for row in buttons_for_event(UiEventKind.GENERATION_FAILED) for b in row]
    assert "retry_generate" in actions
    assert "open_generate" in actions


def test_apply_event_sets_context_phase():
    st = EngineUiState(phase=EngineUiPhase.GEN_CONFIRM)
    st2 = apply_event(st, UiEventKind.GENERATION_FAILED, detail="boom")
    assert st2.phase == EngineUiPhase.CONTEXT
    assert st2.slots["ui_event"] == "generation_failed"
    assert "boom" in st2.slots["ui_event_detail"]


def test_context_buttons_from_state():
    st = apply_event(EngineUiState(), UiEventKind.INSUFFICIENT_QUOTA, detail="limit")
    actions = [b.action for row in buttons_for_state(st) for b in row]
    assert "open_billing" in actions


def test_retry_generate_runs():
    st = apply_event(
        EngineUiState(slots={"bot_description": "بوت فيه /start و /help"}),
        UiEventKind.GENERATION_FAILED,
    )
    r = apply_action(st, "retry_generate")
    assert r.ok
    assert r.run_generation is True
    assert r.state.phase == EngineUiPhase.GENERATING


def test_dismiss_event_home():
    st = apply_event(EngineUiState(), UiEventKind.NO_PROJECT)
    r = apply_action(st, "dismiss_event")
    assert r.state.phase == EngineUiPhase.HOME
