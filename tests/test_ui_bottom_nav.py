"""Deep Navigation — every non-home phase has fixed bottom nav."""
from __future__ import annotations

from lumen.engine.services.ui_state.controller import buttons_for_state, apply_action
from lumen.engine.services.ui_state.models import EngineUiPhase, EngineUiState


def _actions(rows):
    out = []
    for row in rows:
        for b in row:
            out.append(b.action)
    return out


def test_every_non_home_phase_has_nav_footer():
    phases = [
        EngineUiPhase.GEN_TYPE,
        EngineUiPhase.GEN_SLOTS,
        EngineUiPhase.GEN_CONFIRM,
        EngineUiPhase.GENERATING,
        EngineUiPhase.GEN_DONE,
        EngineUiPhase.DASHBOARD,
        EngineUiPhase.BILLING,
        EngineUiPhase.HELP,
    ]
    for phase in phases:
        st = EngineUiState(phase=phase, slots={"bot_type": "custom", "bot_description": "بوت تجريبي"})
        if phase == EngineUiPhase.GEN_SLOTS:
            st.needs = []
            st.missing = []
        acts = _actions(buttons_for_state(st))
        assert "home" in acts, f"{phase} missing home: {acts}"
        if phase != EngineUiPhase.GENERATING:
            assert "nav_back" in acts, f"{phase} missing nav_back: {acts}"
        assert "cancel_generate" in acts, f"{phase} missing cancel: {acts}"
        # footer is last row
        last = buttons_for_state(st)[-1]
        last_acts = [b.action for b in last]
        assert "home" in last_acts


def test_home_has_no_nav_footer():
    rows = buttons_for_state(EngineUiState(phase=EngineUiPhase.HOME))
    acts = _actions(rows)
    assert "nav_back" not in acts
    assert "open_generate" in acts


def test_nav_back_gen_slots_to_type():
    st = EngineUiState(phase=EngineUiPhase.GEN_SLOTS, slots={"bot_type": "custom"})
    res = apply_action(st, "nav_back", "", user_id=1)
    assert res.ok
    assert res.state.phase == EngineUiPhase.GEN_TYPE


def test_nav_back_confirm_to_slots():
    st = EngineUiState(
        phase=EngineUiPhase.GEN_CONFIRM,
        slots={"bot_type": "custom", "bot_description": "بوت متجر"},
    )
    res = apply_action(st, "nav_back", "", user_id=1)
    assert res.ok
    assert res.state.phase == EngineUiPhase.GEN_SLOTS


def test_nav_back_billing_to_home():
    st = EngineUiState(phase=EngineUiPhase.BILLING)
    res = apply_action(st, "nav_back", "", user_id=1)
    assert res.ok
    assert res.state.phase == EngineUiPhase.HOME
