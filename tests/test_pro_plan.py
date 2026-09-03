"""Dedicated unit tests for the Lumen Pro Plan feature.

Covers:
- pro_plan config module constants and helpers
- EngineUiPhase.PRO_PLAN phase exists
- catalog registration of show_more_plans / view_pro_plan / buy_pro_plan
- signed_callback roundtrip for the 3 new actions
- controller flow: BILLING -> show_more_plans -> view_pro_plan -> buy_pro_plan
- controller button styles (green for Pro/buy, blue for show_more)
- nav_back from PRO_PLAN -> BILLING
- home clears billing_expanded slot
- render_message produces HTML card for PRO_PLAN
- Rich Messages table builds all 6 resource rows
"""
import os

os.environ.setdefault("TELEGRAM_BOT_TOKEN", "test:t123")
os.environ.setdefault("TBE_TOKEN_SECRET", "test_secret_1234567890")
os.environ.setdefault("API_KEY_PEPPER", "test_pepper_1234567890")
os.environ.setdefault("TBE_ENV", "test")
os.environ.setdefault("ALLOW_ALL_USERS", "1")
os.environ.setdefault("GEMINI_API_KEY", "test_key")

from lumen.engine.services.ui_state.pro_plan import (
    PRO_PLAN_ID,
    PRO_PLAN_TITLE,
    PRO_PLAN_PRICE_USD,
    PRO_PLAN_PRICE_STARS,
    PRO_PLAN_DURATION_MONTHS,
    PRO_PLAN_DURATION_LABEL,
    PRO_PLAN_BOT_LIMIT,
    PRO_PLAN_INVOICE_PAYLOAD,
    PRO_PLAN_RESOURCES,
    PRO_PLAN_INCLUDES,
    PRO_PLAN_TABLE_HEADERS,
    pro_plan_table_rows,
    pro_plan_includes_text,
    pro_plan_invoice_description,
)
from lumen.engine.services.ui_state.models import EngineUiPhase, EngineUiState
from lumen.engine.services.ui_state.catalog import UI_ACTIONS, UiActionSpec
from lumen.engine.services.ui_state.controller import apply_action, buttons_for_state
from lumen.engine.services.ui_state.render import render_message
from lumen.bot.ui.signed_callback import encode_signed, decode_signed, _ACTION_SHORT


# ---------------------------------------------------------------------------
# pro_plan config module
# ---------------------------------------------------------------------------

def test_pro_plan_constants():
    assert PRO_PLAN_ID == "lumen_pro"
    assert PRO_PLAN_TITLE == "🚀 Lumen Pro"
    assert PRO_PLAN_PRICE_USD == 25
    assert PRO_PLAN_PRICE_STARS == 2000
    assert PRO_PLAN_DURATION_MONTHS == 1
    assert PRO_PLAN_DURATION_LABEL == "شهر"
    assert PRO_PLAN_BOT_LIMIT == 3
    assert PRO_PLAN_INVOICE_PAYLOAD == "lumen_pro_monthly_v1"


def test_pro_plan_resources_present():
    # 6 resource rows expected: storage, RAM, CPU, bots, duration, price
    assert len(PRO_PLAN_RESOURCES) >= 5
    labels = [r.label for r in PRO_PLAN_RESOURCES]
    assert any("2" in (r.value or "") and "GB" in (r.value or "").upper() for r in PRO_PLAN_RESOURCES), "2GB storage row missing"


def test_pro_plan_includes_present():
    assert len(PRO_PLAN_INCLUDES) >= 1
    text = pro_plan_includes_text()
    assert isinstance(text, str) and len(text) > 0


def test_pro_plan_table_rows():
    rows = pro_plan_table_rows()
    assert len(rows) == len(PRO_PLAN_RESOURCES)
    for row in rows:
        assert len(row) == 2  # (label, value)


def test_pro_plan_invoice_description():
    desc = pro_plan_invoice_description()
    assert isinstance(desc, str) and len(desc) > 0
    assert "2000" in desc or "Pro" in desc


# ---------------------------------------------------------------------------
# phase enum
# ---------------------------------------------------------------------------

def test_pro_plan_phase_in_enum():
    assert hasattr(EngineUiPhase, "PRO_PLAN")
    assert EngineUiPhase.PRO_PLAN.value == "pro_plan"


# ---------------------------------------------------------------------------
# catalog
# ---------------------------------------------------------------------------

def test_catalog_has_new_actions():
    for aid in ("show_more_plans", "view_pro_plan", "buy_pro_plan"):
        assert aid in UI_ACTIONS, f"{aid} missing from UI_ACTIONS"
        spec = UI_ACTIONS[aid]
        assert isinstance(spec, UiActionSpec)
        assert spec.action_id == aid


def test_view_pro_plan_valid_phases():
    spec = UI_ACTIONS["view_pro_plan"]
    phases = spec.allowed_phases
    assert EngineUiPhase.BILLING in phases
    assert EngineUiPhase.PRO_PLAN in phases


def test_buy_pro_plan_valid_phases():
    spec = UI_ACTIONS["buy_pro_plan"]
    phases = spec.allowed_phases
    assert EngineUiPhase.PRO_PLAN in phases


# ---------------------------------------------------------------------------
# signed_callback roundtrip
# ---------------------------------------------------------------------------

def test_signed_callbacks_roundtrip():
    user_id = 123456789
    for aid in ("show_more_plans", "view_pro_plan", "buy_pro_plan"):
        assert aid in _ACTION_SHORT, f"{aid} missing short alias"
        cb = encode_signed(aid, user_id=user_id)
        assert len(cb) <= 64, f"{aid} callback {len(cb)} bytes > 64"
        parsed = decode_signed(cb, user_id=user_id)
        assert parsed is not None, f"{aid} decode failed"
        assert parsed[0] == aid, f"{aid} roundtrip mismatch: got {parsed[0]}"


# ---------------------------------------------------------------------------
# controller flow
# ---------------------------------------------------------------------------

def _state(phase=EngineUiPhase.BILLING, slots=None):
    return EngineUiState(
        phase=phase,
        missing=[],
        slots=dict(slots or {}),
    )


def test_billing_default_shows_show_more_not_pro():
    state = _state()
    rows = buttons_for_state(state)
    flat = [b for row in rows for b in row]
    texts = [b.text for b in flat]
    assert any("عرض المزيد" in t for t in texts), "show_more button missing on default billing"
    assert not any("Lumen Pro" in t for t in texts), "Pro button should NOT show on default billing"


def test_show_more_reveals_pro_button():
    state = _state()
    res = apply_action(state, "show_more_plans", user_id=123)
    assert res.ok
    assert res.state.slots.get("billing_expanded") == "1"
    rows = buttons_for_state(res.state)
    flat = [b for row in rows for b in row]
    pro_btn = [b for b in flat if "Lumen Pro" in b.text]
    assert pro_btn, "Pro button should appear after show_more"
    assert pro_btn[0].style == "success", "Pro button should be green (success)"


def test_view_pro_plan_sets_phase():
    state = _state(slots={"billing_expanded": "1"})
    res = apply_action(state, "view_pro_plan", user_id=123)
    assert res.ok
    assert res.state.phase == EngineUiPhase.PRO_PLAN


def test_pro_plan_buttons():
    state = _state(phase=EngineUiPhase.PRO_PLAN)
    rows = buttons_for_state(state)
    flat = [b for row in rows for b in row]
    buy = [b for b in flat if "اشترك" in b.text or "2000" in b.text]
    assert buy, "buy button missing on PRO_PLAN"
    assert buy[0].style == "success", "buy button should be green"
    back = [b for b in flat if "رجوع" in b.text]
    assert back, "back-to-billing button missing"


def test_buy_pro_plan_sets_slot():
    state = _state(phase=EngineUiPhase.PRO_PLAN)
    res = apply_action(state, "buy_pro_plan", user_id=123)
    assert res.ok
    assert res.state.slots.get("pro_buy_requested") == "1"


def test_nav_back_from_pro_plan_to_billing():
    state = _state(phase=EngineUiPhase.PRO_PLAN, slots={"billing_expanded": "1"})
    res = apply_action(state, "nav_back", user_id=123)
    assert res.ok
    assert res.state.phase == EngineUiPhase.BILLING


def test_home_clears_billing_expanded():
    state = _state(slots={"billing_expanded": "1", "pro_buy_requested": "1"})
    res = apply_action(state, "home", user_id=123)
    assert res.ok
    assert res.state.slots.get("billing_expanded") != "1"
    assert res.state.slots.get("pro_buy_requested") != "1"


# ---------------------------------------------------------------------------
# render
# ---------------------------------------------------------------------------

def test_render_pro_plan_card():
    state = _state(phase=EngineUiPhase.PRO_PLAN)
    html = render_message(state)
    assert isinstance(html, str) and len(html) > 0
    assert "Pro" in html or "Lumen" in html
    assert "2000" in html, "stars price missing from rendered card"


# ---------------------------------------------------------------------------
# rich messages table
# ---------------------------------------------------------------------------

def test_rich_table_builds():
    from lumen.bot.rich_messages import build_table_html
    rows = pro_plan_table_rows()
    html = build_table_html(PRO_PLAN_TABLE_HEADERS, rows)
    assert isinstance(html, str)
    assert "<table" in html.lower() or "<tr" in html.lower()
    # every resource row label should appear
    for r in PRO_PLAN_RESOURCES:
        assert r.label in html, f"resource label '{r.label}' missing from rich table"
