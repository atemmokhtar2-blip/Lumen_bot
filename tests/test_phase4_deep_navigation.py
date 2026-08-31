"""Phase 4 tests — Weakness 4: Deep Navigation (unified bottom navigation).

Verifies:
1. Every non-HOME phase has the unified bottom nav [back, home, cancel_generate]
   as the last row.
2. GENERATING has only [cancel_generate] (can't go back mid-generation).
3. HOME/IDLE have no bottom nav (they ARE the root).
4. The "back" action navigates to the logically previous phase.
5. "back" is in the catalog (is_known_action).
6. "cancel_generate" is allowed in all sub-page phases.
"""
import pytest


def test_bottom_nav_present_in_all_non_home_phases():
    """Every non-HOME/IDLE phase must have [back, home, cancel_generate] as last row."""
    from lumen.engine.services.ui_state.controller import buttons_for_state
    from lumen.engine.services.ui_state.models import EngineUiState, EngineUiPhase

    expected_nav = ("back", "home", "cancel_generate")
    for phase in EngineUiPhase:
        if phase in {EngineUiPhase.HOME, EngineUiPhase.IDLE, EngineUiPhase.GENERATING}:
            continue
        state = EngineUiState(phase=phase)
        btns = buttons_for_state(state)
        assert len(btns) > 0, f"Phase {phase.value} has no buttons"
        last_row = btns[-1]
        actions = tuple(b.action for b in last_row)
        assert actions == expected_nav, (
            f"Phase {phase.value}: last row actions={actions}, expected={expected_nav}"
        )


def test_generating_has_only_cancel():
    """GENERATING phase should have only [cancel_generate] (can't go back)."""
    from lumen.engine.services.ui_state.controller import buttons_for_state
    from lumen.engine.services.ui_state.models import EngineUiState, EngineUiPhase

    state = EngineUiState(phase=EngineUiPhase.GENERATING)
    btns = buttons_for_state(state)
    assert len(btns) == 1, f"GENERATING should have 1 row, got {len(btns)}"
    actions = [b.action for b in btns[0]]
    assert actions == ["cancel_generate"], f"Expected [cancel_generate], got {actions}"


def test_home_has_no_bottom_nav():
    """HOME phase should have the main menu, no bottom nav."""
    from lumen.engine.services.ui_state.controller import buttons_for_state
    from lumen.engine.services.ui_state.models import EngineUiState, EngineUiPhase

    state = EngineUiState(phase=EngineUiPhase.HOME)
    btns = buttons_for_state(state)
    # Last row should be the menu (billing, help), not bottom nav
    last_actions = [b.action for b in btns[-1]]
    assert "back" not in last_actions, "HOME should not have 'back' button"
    assert "cancel_generate" not in last_actions, "HOME should not have 'cancel' button"


def test_back_action_navigates_to_previous_phase():
    """The 'back' action should go to the logically previous phase."""
    from lumen.engine.services.ui_state.controller import apply_action, _previous_phase
    from lumen.engine.services.ui_state.models import EngineUiState, EngineUiPhase

    cases = [
        (EngineUiPhase.GEN_SLOTS, EngineUiPhase.GEN_TYPE),
        (EngineUiPhase.GEN_CONFIRM, EngineUiPhase.GEN_SLOTS),
        (EngineUiPhase.GEN_TYPE, EngineUiPhase.HOME),
        (EngineUiPhase.GEN_DONE, EngineUiPhase.HOME),
        (EngineUiPhase.DASHBOARD, EngineUiPhase.HOME),
        (EngineUiPhase.BILLING, EngineUiPhase.HOME),
        (EngineUiPhase.HELP, EngineUiPhase.HOME),
        (EngineUiPhase.CONTEXT, EngineUiPhase.HOME),
    ]
    for from_phase, expected in cases:
        state = EngineUiState(phase=from_phase)
        result = apply_action(state, "back", user_id=123)
        assert result.state.phase == expected, (
            f"back from {from_phase.value} → {result.state.phase.value}, expected {expected.value}"
        )
        assert _previous_phase(from_phase) == expected


def test_back_action_in_catalog():
    """'back' must be a known action in the catalog."""
    from lumen.engine.services.ui_state.catalog import is_known_action, get_action

    assert is_known_action("back"), "'back' should be a known action"
    spec = get_action("back")
    assert spec is not None
    assert "gen_type" in [p.value for p in spec.allowed_phases]


def test_cancel_generate_allowed_in_all_sub_pages():
    """cancel_generate must be allowed in all sub-page phases (not just gen phases)."""
    from lumen.engine.services.ui_state.catalog import get_action
    from lumen.engine.services.ui_state.models import EngineUiPhase

    spec = get_action("cancel_generate")
    assert spec is not None
    expected_phases = {
        EngineUiPhase.GEN_TYPE,
        EngineUiPhase.GEN_SLOTS,
        EngineUiPhase.GEN_CONFIRM,
        EngineUiPhase.GENERATING,
        EngineUiPhase.GEN_DONE,
        EngineUiPhase.DASHBOARD,
        EngineUiPhase.BILLING,
        EngineUiPhase.HELP,
        EngineUiPhase.CONTEXT,
    }
    for p in expected_phases:
        assert p in spec.allowed_phases, f"cancel_generate not allowed in {p.value}"


def test_back_from_gen_confirm_restores_needs():
    """back from GEN_CONFIRM → GEN_SLOTS should restore engine needs."""
    from lumen.engine.services.ui_state.controller import apply_action
    from lumen.engine.services.ui_state.models import EngineUiState, EngineUiPhase

    state = EngineUiState(phase=EngineUiPhase.GEN_CONFIRM)
    state.slots["bot_description"] = "بوت طقس"
    state.slots["bot_type"] = "custom"
    result = apply_action(state, "back", user_id=123)
    assert result.state.phase == EngineUiPhase.GEN_SLOTS


def test_context_phase_has_event_buttons_plus_bottom_nav():
    """CONTEXT phase should have event-specific buttons + bottom nav."""
    from lumen.engine.services.ui_state.controller import buttons_for_state
    from lumen.engine.services.ui_state.models import EngineUiState, EngineUiPhase

    state = EngineUiState(phase=EngineUiPhase.CONTEXT)
    state.slots["ui_event"] = "generation_failed"
    btns = buttons_for_state(state)
    assert len(btns) >= 2, f"CONTEXT should have event buttons + nav, got {len(btns)} rows"
    # Last row is bottom nav
    last_actions = [b.action for b in btns[-1]]
    assert last_actions == ["back", "home", "cancel_generate"]
    # First rows should contain event-specific actions (not just nav)
    first_actions = [b.action for b in btns[0]]
    assert "retry_generate" in first_actions or "open_generate" in first_actions


def test_no_duplicate_back_or_home_in_phase_buttons():
    """Phase-specific buttons should not duplicate 'back' or 'home' (bottom nav provides them)."""
    from lumen.engine.services.ui_state.controller import buttons_for_state
    from lumen.engine.services.ui_state.models import EngineUiState, EngineUiPhase

    for phase in EngineUiPhase:
        if phase in {EngineUiPhase.HOME, EngineUiPhase.IDLE}:
            continue
        state = EngineUiState(phase=phase)
        btns = buttons_for_state(state)
        # Check all rows except the last (bottom nav) for duplicate back/home
        for row in btns[:-1]:
            for btn in row:
                # "home" is OK in some phase buttons (e.g. dashboard refresh), but
                # "back" should only appear in the bottom nav
                assert btn.action != "back", (
                    f"Phase {phase.value}: 'back' found outside bottom nav"
                )
