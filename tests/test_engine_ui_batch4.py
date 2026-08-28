"""Batch 4 — dashboard HostService-backed actions."""
from __future__ import annotations

from lumen.engine.services.ui_state import EngineUiPhase, EngineUiState, apply_action, buttons_for_state


def test_dashboard_buttons_with_host_slots():
    st = EngineUiState(
        phase=EngineUiPhase.DASHBOARD,
        slots={"dash_h0": "inst-abcdef12", "dash_s0": "running"},
    )
    actions = [b.action for row in buttons_for_state(st) for b in row]
    assert "dash_status" in actions
    assert "dash_stop" in actions
    assert "dash_diagnose" in actions
    assert "open_dashboard" in actions


def test_dash_status_sets_effect():
    st = EngineUiState(
        phase=EngineUiPhase.DASHBOARD,
        slots={"dash_h0": "inst-abcdef12", "dash_s0": "running"},
    )
    r = apply_action(st, "dash_status", "abcdef12")
    assert r.ok
    assert r.dash_effect == "dash_status"
    assert r.dash_target == "abcdef12"


def test_resolve_instance_id():
    from lumen.bot.ui.dash_actions import resolve_instance_id
    slots = {"dash_h0": "host-xyz-abcdef12"}
    assert resolve_instance_id("abcdef12", slots) == "host-xyz-abcdef12"


def test_sync_dashboard_slots_no_crash():
    from lumen.bot.ui.dash_actions import sync_dashboard_slots
    slots = sync_dashboard_slots(0, {})
    assert isinstance(slots, dict)
