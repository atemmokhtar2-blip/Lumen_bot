"""Batch 0 — engine UI state foundation (no generation side effects)."""
from __future__ import annotations

import pytest

from lumen.engine.services.ui_state import (
    EngineUiPhase,
    EngineUiState,
    apply_action,
    buttons_for_phase,
    is_known_action,
    missing_for_state,
)
from lumen.bot.ui.keyboards import decode_callback, encode_callback
from lumen.bot.ui.state_store import load_ui_state, save_ui_state


def test_unknown_action_fail_closed():
    st = EngineUiState(phase=EngineUiPhase.HOME)
    r = apply_action(st, "pay_now")
    assert r.ok is False
    assert r.state.phase == EngineUiPhase.HOME


def test_home_to_generate_shell():
    st = EngineUiState(phase=EngineUiPhase.HOME)
    r = apply_action(st, "open_generate")
    assert r.ok is True
    assert r.state.phase == EngineUiPhase.GEN_TYPE
    assert "bot_type" in missing_for_state(r.state)


def test_action_not_allowed_in_phase():
    st = EngineUiState(phase=EngineUiPhase.GENERATING)
    r = apply_action(st, "confirm_generate")
    assert r.ok is False
    assert r.state.phase == EngineUiPhase.GENERATING


def test_buttons_encode_under_64_bytes():
    rows = buttons_for_phase(EngineUiPhase.HOME)
    for row in rows:
        for btn in row:
            data = encode_callback(btn.action, btn.arg)
            assert len(data.encode("utf-8")) <= 64
            parsed = decode_callback(data)
            assert parsed is not None
            assert parsed[0] == btn.action


def test_decode_rejects_foreign_namespace():
    assert decode_callback("other:pay") is None
    assert decode_callback("") is None


def test_state_roundtrip_user_data():
    ud: dict = {}
    st = EngineUiState(phase=EngineUiPhase.DASHBOARD, project_ref="/tmp/p")
    save_ui_state(ud, st)
    loaded = load_ui_state(ud)
    assert loaded.phase == EngineUiPhase.DASHBOARD
    assert loaded.project_ref == "/tmp/p"


def test_catalog_closed():
    assert is_known_action("home")
    assert not is_known_action("stripe_checkout")


def test_from_dict_invalid_phase_defaults_home():
    st = EngineUiState.from_dict({"phase": "not_a_real_phase"})
    assert st.phase == EngineUiPhase.HOME

def test_render_dashboard_lists_hosts():
    from lumen.engine.services.ui_state import EngineUiPhase, EngineUiState, HostRow, UiFacts, render_message
    st = EngineUiState(phase=EngineUiPhase.DASHBOARD)
    facts = UiFacts(
        hosts=[HostRow("host-1", "running", "mybot", "firecracker")],
        active_project="/data/u1/bot",
    )
    text = render_message(st, facts)
    assert "host-1" in text
    assert "running" in text
    assert "firecracker" in text
    assert "/data/u1/bot" in text


def test_render_billing_no_fake_payment():
    from lumen.engine.services.ui_state import EngineUiPhase, EngineUiState, UiFacts, render_message
    st = EngineUiState(phase=EngineUiPhase.BILLING)
    facts = UiFacts(plan_label="Free — مجاني", generations_per_month="10", hosted_bots_limit="1")
    text = render_message(st, facts)
    assert "Free" in text
    assert "10" in text
    assert "دفع" in text  # honest note that payment UI is not live


def test_open_generate_sets_awaiting_text():
    from lumen.engine.services.ui_state import EngineUiPhase, EngineUiState, apply_action
    r = apply_action(EngineUiState(phase=EngineUiPhase.HOME), "open_generate")
    assert r.ok
    assert r.state.phase == EngineUiPhase.GEN_TYPE
    # awaiting_text is set when user picks custom, not on open_generate
    r2 = apply_action(r.state, "pick_type", "custom")
    assert r2.state.slots.get("awaiting_text") == "1"


def test_encode_await_generate():
    from lumen.bot.ui.keyboards import encode_callback, decode_callback
    d = encode_callback("await_generate_text")
    assert decode_callback(d) == ("await_generate_text", "")
