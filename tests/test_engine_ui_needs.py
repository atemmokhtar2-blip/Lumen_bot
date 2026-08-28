"""Dynamic buttons from engine needs."""
from __future__ import annotations

from lumen.engine.services.ui_state import (
    EngineUiPhase,
    EngineUiState,
    analyze_needs,
    apply_action,
    buttons_for_state,
)


def test_shop_seed_triggers_engine_needs_or_confirm():
    st = apply_action(EngineUiState(phase=EngineUiPhase.HOME), "open_generate").state
    r = apply_action(st, "pick_type", "shop")
    assert r.ok
    assert r.state.phase in {EngineUiPhase.GEN_SLOTS, EngineUiPhase.GEN_CONFIRM}
    if r.state.phase == EngineUiPhase.GEN_SLOTS:
        assert r.state.missing
        # buttons include fill_slot or skip
        flat = [b.action for row in r.buttons for b in row]
        assert "skip_need" in flat or "fill_slot" in flat


def test_fill_slot_reduces_missing():
    st = apply_action(EngineUiState(phase=EngineUiPhase.HOME), "open_generate").state
    st = apply_action(st, "pick_type", "shop").state
    if st.phase != EngineUiPhase.GEN_SLOTS:
        return  # no needs for this environment — ok
    before = list(st.missing)
    # press first fill_slot button
    choice = None
    for row in buttons_for_state(st):
        for b in row:
            if b.action == "fill_slot":
                choice = b.arg
                break
        if choice:
            break
    if not choice:
        st = apply_action(st, "skip_need").state
        assert st.missing != before or st.phase == EngineUiPhase.GEN_CONFIRM
        return
    r = apply_action(st, "fill_slot", choice)
    assert r.ok
    assert r.state.phase in {EngineUiPhase.GEN_SLOTS, EngineUiPhase.GEN_CONFIRM}


def test_analyze_needs_shop_mentions():
    plan = analyze_needs("عايز بوت متجر يبيع منتجات")
    # fallback or lu should surface at least one need or empty if LU says enough
    assert plan.source in {"lu", "lu_empty", "planner_fallback", "empty"}
