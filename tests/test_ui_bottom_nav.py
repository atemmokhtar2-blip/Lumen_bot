"""Deep Navigation — fixed bottom nav on every interactive surface."""
from __future__ import annotations

from lumen.engine.services.ui_state.controller import buttons_for_state, apply_action
from lumen.engine.services.ui_state.models import EngineUiPhase, EngineUiState, UiButton
from lumen.engine.services.ui_state.nav import with_nav, nav_footer, last_row_is_nav


def _actions(rows):
    return [b.action for row in rows for b in row]


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
        st = EngineUiState(
            phase=phase,
            slots={"bot_type": "custom", "bot_description": "بوت تجريبي"},
        )
        acts = _actions(buttons_for_state(st))
        assert "home" in acts, f"{phase} missing home: {acts}"
        assert "cancel_generate" in acts, f"{phase} missing cancel: {acts}"
        if phase != EngineUiPhase.GENERATING:
            assert "nav_back" in acts, f"{phase} missing nav_back: {acts}"
        last = buttons_for_state(st)[-1]
        assert "home" in [b.action for b in last]


def test_home_has_no_nav_footer():
    rows = buttons_for_state(EngineUiState(phase=EngineUiPhase.HOME))
    assert "nav_back" not in _actions(rows)
    assert "open_generate" in _actions(rows)


def test_with_nav_on_host_like_rows():
    rows = (
        (UiButton("حالة", "dash_status", "0"),),
        (UiButton("إيقاف", "dash_stop", "0", style="danger"),),
    )
    out = with_nav(rows, EngineUiPhase.DASHBOARD)
    assert last_row_is_nav(out)
    assert "dash_status" in _actions(out)
    assert _actions(out).count("home") == 1  # no duplicates


def test_nav_back_paths():
    st = EngineUiState(phase=EngineUiPhase.GEN_SLOTS, slots={"bot_type": "custom"})
    assert apply_action(st, "nav_back", "", user_id=1).state.phase == EngineUiPhase.GEN_TYPE

    st = EngineUiState(
        phase=EngineUiPhase.GEN_CONFIRM,
        slots={"bot_type": "custom", "bot_description": "x"},
    )
    assert apply_action(st, "nav_back", "", user_id=1).state.phase == EngineUiPhase.GEN_SLOTS

    st = EngineUiState(phase=EngineUiPhase.BILLING)
    assert apply_action(st, "nav_back", "", user_id=1).state.phase == EngineUiPhase.HOME


def test_cancel_from_billing_goes_home():
    st = EngineUiState(phase=EngineUiPhase.BILLING)
    res = apply_action(st, "cancel_generate", "", user_id=1)
    assert res.ok
    assert res.state.phase == EngineUiPhase.HOME


def test_keyboards_source_auto_nav_logic():
    """build_inline_keyboard source must wire with_nav / last_row_is_nav."""
    src = open("lumen/bot/ui/keyboards.py", encoding="utf-8").read()
    assert "with_nav" in src and "last_row_is_nav" in src
    assert 'nav: bool | str = "auto"' in src
    # simulate auto path using with_nav (same as keyboards when nav=True)
    rows = ((UiButton("حالة", "dash_status", "0"),),)
    out = with_nav(rows, "context")
    assert last_row_is_nav(out)


def test_commands_home_disables_nav():
    src = open("lumen/bot/commands.py", encoding="utf-8").read()
    assert "nav=False" in src
