"""Batch 4 — dashboard HostService-backed actions (index targets)."""
from __future__ import annotations

from lumen.engine.services.ui_state import EngineUiPhase, EngineUiState, apply_action, buttons_for_state


def test_dashboard_buttons_with_host_slots():
    st = EngineUiState(
        phase=EngineUiPhase.DASHBOARD,
        slots={"dash_h0": "inst-abcdef12", "dash_s0": "running", "dash_u0": "mybot"},
    )
    actions = [b.action for row in buttons_for_state(st) for b in row]
    assert "dash_status" in actions
    assert "dash_stop" in actions
    assert "dash_diagnose" in actions
    args = [b.arg for row in buttons_for_state(st) for b in row if b.action == "dash_stop"]
    assert "0" in args


def test_dash_status_sets_effect():
    st = EngineUiState(
        phase=EngineUiPhase.DASHBOARD,
        slots={"dash_h0": "inst-abcdef12", "dash_s0": "running"},
    )
    r = apply_action(st, "dash_status", "0")
    assert r.ok
    assert r.dash_effect == "dash_status"
    assert r.dash_target == "0"


def test_resolve_instance_id_by_index():
    from lumen.bot.ui.dash_actions import resolve_instance_id
    slots = {"dash_h0": "host-xyz-abcdef12"}
    assert resolve_instance_id("0", slots) == "host-xyz-abcdef12"
    assert resolve_instance_id("abcdef12", slots) == "host-xyz-abcdef12"


def test_sync_dashboard_slots_no_crash():
    from lumen.bot.ui.dash_actions import sync_dashboard_slots
    slots = sync_dashboard_slots(0, {"keep": "1"})
    assert slots.get("keep") == "1"
    assert "dash_count" in slots


def test_format_host_result():
    from types import SimpleNamespace
    from lumen.bot.ui.dash_actions import format_host_result
    inst = SimpleNamespace(
        instance_id="i1", status="running", bot_username="b",
        sandbox_backend="firecracker", project_path="/p", last_error="", pid=1,
    )
    r = SimpleNamespace(ok=True, message="ok", instance=inst, error_contract=None)
    text = format_host_result(r)
    assert "running" in text and "firecracker" in text
