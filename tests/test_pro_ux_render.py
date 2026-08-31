"""Professional UX render tests — verify every screen is clear, welcoming,
actionable, and free of exposed technical jargon.

These tests enforce the world-class UX standard:
  - Arabic text is professional and human-readable
  - Emojis are used as visual section markers
  - No internal technical jargon exposed (HostService, instance, plane, etc.)
  - Server filesystem paths are masked
  - Internal slot keys are translated to human labels
  - Each screen provides actionable guidance
"""
from __future__ import annotations

import pytest

from lumen.engine.services.ui_state import (
    EngineUiPhase,
    EngineUiState,
    HostRow,
    UiFacts,
    render_message,
)
from lumen.engine.services.ui_state.engine_needs import EngineNeed, NeedChoice


# ---------------------------------------------------------------------------
# Jargon that must NEVER appear in user-facing text
# ---------------------------------------------------------------------------
FORBIDDEN_JARGON = [
    "HostService",
    "instance",
    "plane",
    "intent_kind",
    "slots",
    "RuntimePlaneHint",
    "EngineUiPhase",
    "UiActionSpec",
    "awaiting_text",
    "awaiting_slot",
    "needs_json",
    "ui_event",
    "firecracker",
    "jailer",
    "cline",
]


def _assert_no_jargon(text: str):
    """Assert no technical jargon is exposed to the user."""
    lower = text.lower()
    for word in FORBIDDEN_JARGON:
        assert word.lower() not in lower, f"Forbidden jargon '{word}' found in: {text[:200]}"


def _need(slot: str, text: str, choices=None) -> dict:
    """Build a need dict as stored in state.needs."""
    n = EngineNeed(slot=slot, text=text, choices=choices or [])
    return n.to_dict()


# ---------------------------------------------------------------------------
# HOME
# ---------------------------------------------------------------------------
class TestHomeRender:
    def test_home_is_welcoming(self):
        facts = UiFacts(credits_available=100)
        text = render_message(EngineUiState(phase=EngineUiPhase.HOME), facts)
        assert "Lumen" in text
        assert "أهلاً" in text or "اهلا" in text

    def test_home_explains_what_lumen_does(self):
        facts = UiFacts()
        text = render_message(EngineUiState(phase=EngineUiPhase.HOME), facts)
        assert "بوت" in text
        assert "تيليجرام" in text or "تيليغرام" in text

    def test_home_shows_examples(self):
        facts = UiFacts()
        text = render_message(EngineUiState(phase=EngineUiPhase.HOME), facts)
        assert "أمثلة" in text or "امثلة" in text
        assert "متجر" in text or "تذكير" in text

    def test_home_shows_credits(self):
        facts = UiFacts(credits_available=250)
        text = render_message(EngineUiState(phase=EngineUiPhase.HOME), facts)
        assert "250" in text
        assert "كريديت" in text

    def test_home_invites_action(self):
        facts = UiFacts()
        text = render_message(EngineUiState(phase=EngineUiPhase.HOME), facts)
        assert "اختر" in text or "اختار" in text
        assert "👇" in text

    def test_home_no_jargon(self):
        facts = UiFacts()
        text = render_message(EngineUiState(phase=EngineUiPhase.HOME), facts)
        _assert_no_jargon(text)

    def test_home_has_emoji_markers(self):
        facts = UiFacts()
        text = render_message(EngineUiState(phase=EngineUiPhase.HOME), facts)
        assert "🤖" in text or "💡" in text or "💎" in text


# ---------------------------------------------------------------------------
# GEN_TYPE
# ---------------------------------------------------------------------------
class TestGenTypeRender:
    def test_gen_type_clear_instruction(self):
        text = render_message(EngineUiState(phase=EngineUiPhase.GEN_TYPE), UiFacts())
        assert "وصف" in text or "صِف" in text
        assert "بوت" in text

    def test_gen_type_has_examples(self):
        text = render_message(EngineUiState(phase=EngineUiPhase.GEN_TYPE), UiFacts())
        assert "أمثلة" in text or "امثلة" in text

    def test_gen_type_guides_to_chat(self):
        text = render_message(EngineUiState(phase=EngineUiPhase.GEN_TYPE), UiFacts())
        assert "اكتب" in text
        assert "👇" in text

    def test_gen_type_no_dry_jargon(self):
        text = render_message(EngineUiState(phase=EngineUiPhase.GEN_TYPE), UiFacts())
        # Old text had "اكتب وصف البوت." — new text should be richer
        assert len(text) > 50
        _assert_no_jargon(text)


# ---------------------------------------------------------------------------
# GEN_SLOTS
# ---------------------------------------------------------------------------
class TestGenSlotsRender:
    def test_gen_slots_clear_question(self):
        state = EngineUiState(
            phase=EngineUiPhase.GEN_SLOTS,
            needs=[_need("payment", "كيف سيتم الدفع؟", [])],
            slots={"bot_description": "بوت متجر"},
        )
        text = render_message(state, UiFacts())
        assert "الدفع" in text or "دفع" in text
        assert "؟" in text or "?" in text

    def test_gen_slots_shows_progress(self):
        state = EngineUiState(
            phase=EngineUiPhase.GEN_SLOTS,
            needs=[
                _need("payment", "كيف سيتم الدفع؟", []),
                _need("language", "ما اللغة؟", []),
            ],
            slots={"bot_description": "بوت متجر"},
        )
        text = render_message(state, UiFacts())
        # Should show question number like "السؤال 1 من 2"
        assert "1" in text
        assert "2" in text

    def test_gen_slots_shows_filled_summary(self):
        state = EngineUiState(
            phase=EngineUiPhase.GEN_SLOTS,
            needs=[_need("language", "ما اللغة؟", [])],
            slots={"bot_description": "بوت متجر", "payment": "vodafone_cash"},
        )
        text = render_message(state, UiFacts())
        # Should show what's already filled with human label
        assert "فودافون" in text or "الدفع" in text

    def test_gen_slots_no_jargon(self):
        state = EngineUiState(
            phase=EngineUiPhase.GEN_SLOTS,
            needs=[_need("payment", "كيف سيتم الدفع؟", [])],
            slots={"bot_description": "بوت متجر"},
        )
        text = render_message(state, UiFacts())
        _assert_no_jargon(text)


# ---------------------------------------------------------------------------
# GEN_CONFIRM
# ---------------------------------------------------------------------------
class TestGenConfirmRender:
    def test_gen_confirm_shows_summary(self):
        state = EngineUiState(
            phase=EngineUiPhase.GEN_CONFIRM,
            slots={"bot_description": "بوت متجر ملابس"},
        )
        text = render_message(state, UiFacts())
        assert "ملخص" in text or "تأكيد" in text
        assert "بوت متجر ملابس" in text

    def test_gen_confirm_asks_to_proceed(self):
        state = EngineUiState(
            phase=EngineUiPhase.GEN_CONFIRM,
            slots={"bot_description": "بوت متجر"},
        )
        text = render_message(state, UiFacts())
        assert "بدء" in text or "ابدأ" in text or "توليد" in text

    def test_gen_confirm_no_jargon(self):
        state = EngineUiState(
            phase=EngineUiPhase.GEN_CONFIRM,
            slots={"bot_description": "بوت متجر"},
        )
        text = render_message(state, UiFacts())
        _assert_no_jargon(text)


# ---------------------------------------------------------------------------
# GENERATING
# ---------------------------------------------------------------------------
class TestGeneratingRender:
    def test_generating_shows_stages(self):
        text = render_message(EngineUiState(phase=EngineUiPhase.GENERATING), UiFacts())
        assert "جار" in text or "جاري" in text
        # Should mention what the engine is doing
        assert "كود" in text or "كتابة" in text or "اختبار" in text

    def test_generating_shows_time_estimate(self):
        text = render_message(EngineUiState(phase=EngineUiPhase.GENERATING), UiFacts())
        assert "دقيقة" in text or "دقائق" in text

    def test_generating_no_jargon(self):
        text = render_message(EngineUiState(phase=EngineUiPhase.GENERATING), UiFacts())
        _assert_no_jargon(text)


# ---------------------------------------------------------------------------
# GEN_DONE
# ---------------------------------------------------------------------------
class TestGenDoneRender:
    def test_gen_done_celebrates(self):
        state = EngineUiState(phase=EngineUiPhase.GEN_DONE, project_ref="/data/u1/mybot")
        text = render_message(state, UiFacts())
        assert "🎉" in text or "نجاح" in text or "تم" in text

    def test_gen_done_shows_next_steps(self):
        state = EngineUiState(phase=EngineUiPhase.GEN_DONE, project_ref="/data/u1/mybot")
        text = render_message(state, UiFacts())
        assert "جرّب" in text or "جرب" in text or "استضافة" in text or "تحميل" in text

    def test_gen_done_masks_project_path(self):
        state = EngineUiState(phase=EngineUiPhase.GEN_DONE, project_ref="/data/u1/mybot")
        text = render_message(state, UiFacts())
        assert "mybot" in text  # folder name shown
        assert "/data/u1/" not in text  # server path hidden

    def test_gen_done_no_jargon(self):
        state = EngineUiState(phase=EngineUiPhase.GEN_DONE, project_ref="/data/u1/mybot")
        text = render_message(state, UiFacts())
        _assert_no_jargon(text)


# ---------------------------------------------------------------------------
# DASHBOARD
# ---------------------------------------------------------------------------
class TestDashboardRender:
    def test_dashboard_shows_bots(self):
        state = EngineUiState(phase=EngineUiPhase.DASHBOARD)
        facts = UiFacts(hosts=[HostRow("host-abc123", "running", "mybot", "firecracker")])
        text = render_message(state, facts)
        assert "mybot" in text

    def test_dashboard_translates_status(self):
        state = EngineUiState(phase=EngineUiPhase.DASHBOARD)
        facts = UiFacts(hosts=[HostRow("host-1", "running", "mybot", "firecracker")])
        text = render_message(state, facts)
        assert "يعمل" in text  # Arabic for "running"
        assert "🟢" in text

    def test_dashboard_masks_paths(self):
        state = EngineUiState(phase=EngineUiPhase.DASHBOARD)
        facts = UiFacts(active_project="/data/u1/mybot")
        text = render_message(state, facts)
        assert "mybot" in text
        assert "/data/u1/" not in text

    def test_dashboard_no_jargon(self):
        state = EngineUiState(phase=EngineUiPhase.DASHBOARD)
        facts = UiFacts(hosts=[HostRow("host-1", "running", "mybot", "firecracker")])
        text = render_message(state, facts)
        _assert_no_jargon(text)

    def test_dashboard_empty_state(self):
        state = EngineUiState(phase=EngineUiPhase.DASHBOARD)
        facts = UiFacts(hosts=[])
        text = render_message(state, facts)
        assert "لا" in text or "بدون" in text or "فارغ" in text


# ---------------------------------------------------------------------------
# BILLING
# ---------------------------------------------------------------------------
class TestBillingRender:
    def test_billing_shows_balance(self):
        facts = UiFacts(credits_available=100)
        text = render_message(EngineUiState(phase=EngineUiPhase.BILLING), facts)
        assert "100" in text
        assert "كريديت" in text

    def test_billing_shows_cost_breakdown(self):
        facts = UiFacts(credits_available=100, gen_cost_credits=50, host_hourly_credits=10)
        text = render_message(EngineUiState(phase=EngineUiPhase.BILLING), facts)
        assert "50" in text  # generation cost
        assert "10" in text  # hosting cost
        assert "توليد" in text or "استضافة" in text

    def test_billing_no_fake_payment(self):
        facts = UiFacts(credits_available=100)
        text = render_message(EngineUiState(phase=EngineUiPhase.BILLING), facts)
        lower = text.lower()
        assert "checkout" not in lower
        assert "stripe" not in lower
        assert "paypal" not in lower

    def test_billing_no_jargon(self):
        facts = UiFacts(credits_available=100)
        text = render_message(EngineUiState(phase=EngineUiPhase.BILLING), facts)
        _assert_no_jargon(text)


# ---------------------------------------------------------------------------
# HELP
# ---------------------------------------------------------------------------
class TestHelpRender:
    def test_help_is_comprehensive(self):
        text = render_message(EngineUiState(phase=EngineUiPhase.HELP), UiFacts())
        assert "Lumen" in text
        assert len(text) > 200  # comprehensive, not just 4 bullets

    def test_help_organized_sections(self):
        text = render_message(EngineUiState(phase=EngineUiPhase.HELP), UiFacts())
        assert "ما هو" in text or "ماذا" in text  # What is section
        assert "كيف" in text  # How to section
        assert "نصائح" in text or "نصيحة" in text  # Tips section

    def test_help_lists_capabilities(self):
        text = render_message(EngineUiState(phase=EngineUiPhase.HELP), UiFacts())
        assert "متجر" in text
        assert "تذكير" in text or "إشعار" in text
        assert "مهام" in text

    def test_help_no_jargon(self):
        text = render_message(EngineUiState(phase=EngineUiPhase.HELP), UiFacts())
        _assert_no_jargon(text)
