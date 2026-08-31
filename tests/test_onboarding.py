"""Tests for the first-time onboarding flow.

Verifies that:
  1. First-time users see a rich onboarding message (render_onboarding).
  2. Returning users see the compact home menu (render_message → _render_home).
  3. The ``lumen_welcome_shown`` flag correctly distinguishes the two.
  4. Onboarding contains richer content than home (more lines, examples,
     how-it-works steps, differentiation).
  5. No technical jargon leaks into either message.
  6. Onboarding shows exactly once — second /start gets home.
"""
from __future__ import annotations

import pytest

from lumen.engine.services.ui_state.render import (
    render_onboarding,
    render_message,
    UiFacts,
)
from lumen.engine.services.ui_state.models import EngineUiState, EngineUiPhase

# Same jargon block used in test_pro_ux_render.py — no internal terms leak.
FORBIDDEN_JARGON = [
    "HostService", "instance", "plane", "intent_kind", "slots",
    "RuntimePlaneHint", "EngineUiPhase", "UiActionSpec",
    "awaiting_text", "awaiting_slot", "needs_json", "ui_event",
    "firecracker", "jailer", "cline",
]


def _assert_no_jargon(text: str) -> None:
    for word in FORBIDDEN_JARGON:
        assert word not in text, f"Jargon '{word}' leaked into user-facing text: {text[:120]}..."


# ---------------------------------------------------------------------------
# Onboarding message content
# ---------------------------------------------------------------------------

class TestOnboardingContent:
    """render_onboarding must produce a rich, welcoming first-time message."""

    def test_returns_non_empty_string(self):
        text = render_onboarding(UiFacts())
        assert isinstance(text, str)
        assert len(text) > 200  # rich content, not a one-liner

    def test_welcoming_greeting(self):
        text = render_onboarding(UiFacts())
        assert "أهلاً" in text or "مرحباً" in text

    def test_explains_what_lumen_is(self):
        text = render_onboarding(UiFacts())
        assert "Lumen" in text
        # Must mention bots / telegram
        assert "بوت" in text
        assert "تيليجرام" in text

    def test_explains_how_it_works(self):
        text = render_onboarding(UiFacts())
        # Step-by-step explanation
        assert "1️⃣" in text
        assert "2️⃣" in text
        assert "3️⃣" in text

    def test_has_multiple_examples(self):
        text = render_onboarding(UiFacts())
        # At least 5 example bots with emojis
        assert text.count("•") >= 5

    def test_has_invitation_to_try(self):
        text = render_onboarding(UiFacts())
        assert "ابدأ" in text or "جرّب" in text or "تجرب" in text

    def test_mentions_credits(self):
        facts = UiFacts(credits_available=100)
        text = render_onboarding(facts)
        assert "100" in text
        assert "كريديت" in text

    def test_shows_zero_credits_for_new_user(self):
        facts = UiFacts(credits_available=0)
        text = render_onboarding(facts)
        assert "0" in text

    def test_no_jargon(self):
        text = render_onboarding(UiFacts())
        _assert_no_jargon(text)

    def test_no_english_only_jargon(self):
        text = render_onboarding(UiFacts())
        # Should not contain raw English technical words
        for bad in ["HostService", "RuntimePlane", "EngineUiPhase", "UiActionSpec"]:
            assert bad not in text

    def test_mentions_no_coding_required(self):
        text = render_onboarding(UiFacts())
        assert "برمج" in text or "كود" in text or "سطر" in text

    def test_has_differentiation_section(self):
        text = render_onboarding(UiFacts())
        assert "يميّز" in text or "يزيد" in text or "مختلف" in text

    def test_points_to_action_button(self):
        text = render_onboarding(UiFacts())
        assert "👇" in text

    def test_uses_emojis_as_section_markers(self):
        text = render_onboarding(UiFacts())
        # Should have section emojis
        assert any(e in text for e in ["🔬", "💡", "✨", "🎁", "👋"])


# ---------------------------------------------------------------------------
# Onboarding vs Home — onboarding must be richer
# ---------------------------------------------------------------------------

class TestOnboardingVsHome:
    """Onboarding must be more detailed than the compact home menu."""

    def test_onboarding_is_longer_than_home(self):
        facts = UiFacts()
        onboarding = render_onboarding(facts)
        home = render_message(EngineUiState(phase=EngineUiPhase.HOME), facts)
        assert len(onboarding) > len(home), (
            f"Onboarding ({len(onboarding)} chars) should be richer than "
            f"home ({len(home)} chars)"
        )

    def test_onboarding_has_more_examples_than_home(self):
        facts = UiFacts()
        onboarding = render_onboarding(facts)
        home = render_message(EngineUiState(phase=EngineUiPhase.HOME), facts)
        assert onboarding.count("•") > home.count("•"), (
            f"Onboarding should have more examples ({onboarding.count('•')}) "
            f"than home ({home.count('•')})"
        )

    def test_onboarding_has_how_it_works_home_does_not(self):
        facts = UiFacts()
        onboarding = render_onboarding(facts)
        home = render_message(EngineUiState(phase=EngineUiPhase.HOME), facts)
        # Onboarding has numbered steps
        assert "1️⃣" in onboarding
        # Home is compact — no step-by-step
        assert "1️⃣" not in home

    def test_home_is_compact(self):
        """Home menu should be shorter — quick reference for returning users."""
        facts = UiFacts()
        home = render_message(EngineUiState(phase=EngineUiPhase.HOME), facts)
        # Home should be reasonably compact (under ~500 chars)
        assert len(home) < 600, f"Home should be compact, got {len(home)} chars"

    def test_both_show_credits(self):
        facts = UiFacts(credits_available=100)
        onboarding = render_onboarding(facts)
        home = render_message(EngineUiState(phase=EngineUiPhase.HOME), facts)
        assert "100" in onboarding
        assert "100" in home


# ---------------------------------------------------------------------------
# Onboarding shows once — simulation of the start_cmd flow
# ---------------------------------------------------------------------------

class TestOnboardingShowsOnce:
    """Simulate the first /start vs second /start behavior.

    The start_cmd handler checks ``lumen_welcome_shown``:
      - First /start: flag is False → render_onboarding, then set flag
      - Second /start: flag is True → render_message (compact home)
    """

    def test_first_start_gets_onboarding(self):
        """First /start: no welcome flag → onboarding message."""
        ud: dict = {}
        already_welcomed = bool(ud.get("lumen_welcome_shown"))
        assert already_welcomed is False

        facts = UiFacts()
        if already_welcomed:
            caption = render_message(EngineUiState(phase=EngineUiPhase.HOME), facts)
        else:
            caption = render_onboarding(facts)

        # Should contain onboarding-specific markers
        assert "1️⃣" in caption
        assert "كيف" in caption or "يعمل" in caption

    def test_second_start_gets_home(self):
        """Second /start: welcome flag set → compact home."""
        ud = {"lumen_welcome_shown": True}
        already_welcomed = bool(ud.get("lumen_welcome_shown"))
        assert already_welcomed is True

        facts = UiFacts()
        if already_welcomed:
            caption = render_message(EngineUiState(phase=EngineUiPhase.HOME), facts)
        else:
            caption = render_onboarding(facts)

        # Should contain home-specific markers, NOT onboarding markers
        assert "أهلاً بك في Lumen" in caption
        # No step-by-step in compact home
        assert "1️⃣" not in caption

    def test_onboarding_flag_set_after_first_start(self):
        """Simulate the full flow: start → onboarding → set flag → start → home."""
        ud: dict = {}
        facts = UiFacts()

        # First /start
        already_welcomed = bool(ud.get("lumen_welcome_shown"))
        first_caption = render_onboarding(facts) if not already_welcomed else render_message(
            EngineUiState(phase=EngineUiPhase.HOME), facts
        )
        # Simulate setting the flag (as start_cmd does)
        ud["lumen_welcome_shown"] = True

        # Second /start
        already_welcomed_2 = bool(ud.get("lumen_welcome_shown"))
        second_caption = render_onboarding(facts) if not already_welcomed_2 else render_message(
            EngineUiState(phase=EngineUiPhase.HOME), facts
        )

        # First should be onboarding, second should be home
        assert "1️⃣" in first_caption
        assert "1️⃣" not in second_caption
        assert first_caption != second_caption

    def test_onboarding_shows_exactly_once_across_three_starts(self):
        """Three consecutive /start calls → onboarding only on the first."""
        ud: dict = {}
        facts = UiFacts()
        captions = []

        for _ in range(3):
            already_welcomed = bool(ud.get("lumen_welcome_shown"))
            if already_welcomed:
                caption = render_message(EngineUiState(phase=EngineUiPhase.HOME), facts)
            else:
                caption = render_onboarding(facts)
            captions.append(caption)
            ud["lumen_welcome_shown"] = True  # set after first

        # First: onboarding (has steps)
        assert "1️⃣" in captions[0]
        # Second: home (no steps)
        assert "1️⃣" not in captions[1]
        # Third: home (same as second)
        assert "1️⃣" not in captions[2]
        assert captions[1] == captions[2]

    def test_flag_survives_simulated_restart(self):
        """Flag is in user_data dict — persists across 'restarts' (new dicts
        loaded from session store)."""
        # Simulate what session_store does: save → load
        ud: dict = {}
        ud["lumen_welcome_shown"] = True
        # Simulate restart: load from "session store" (just the dict)
        restored = {"lumen_welcome_shown": True}
        already_welcomed = bool(restored.get("lumen_welcome_shown"))
        assert already_welcomed is True

        facts = UiFacts()
        caption = render_message(EngineUiState(phase=EngineUiPhase.HOME), facts) if already_welcomed else render_onboarding(facts)
        # Should be home, not onboarding
        assert "1️⃣" not in caption


# ---------------------------------------------------------------------------
# Both messages must be jargon-free
# ---------------------------------------------------------------------------

class TestNoJargonBothMessages:
    """Both onboarding and home must be free of technical jargon."""

    def test_onboarding_no_jargon(self):
        text = render_onboarding(UiFacts())
        _assert_no_jargon(text)

    def test_home_no_jargon(self):
        text = render_message(EngineUiState(phase=EngineUiPhase.HOME), UiFacts())
        _assert_no_jargon(text)

    def test_onboarding_no_server_paths(self):
        text = render_onboarding(UiFacts())
        assert "/data/" not in text
        assert "firecracker" not in text
        assert "/workspace" not in text

    def test_home_no_server_paths(self):
        text = render_message(EngineUiState(phase=EngineUiPhase.HOME), UiFacts())
        assert "/data/" not in text
        assert "firecracker" not in text
        assert "/workspace" not in text


# ---------------------------------------------------------------------------
# Credits display in onboarding
# ---------------------------------------------------------------------------

class TestOnboardingCredits:
    """Onboarding must correctly display the user's credit balance."""

    def test_zero_credits(self):
        facts = UiFacts(credits_available=0)
        text = render_onboarding(facts)
        assert "0" in text
        assert "كريديت" in text

    def test_one_hundred_credits(self):
        facts = UiFacts(credits_available=100)
        text = render_onboarding(facts)
        assert "100" in text

    def test_large_credits(self):
        facts = UiFacts(credits_available=99999)
        text = render_onboarding(facts)
        assert "99999" in text

    def test_falls_back_to_balance(self):
        """If credits_available is 0 but credits_balance is set, use balance."""
        facts = UiFacts(credits_available=0, credits_balance=50)
        text = render_onboarding(facts)
        assert "50" in text
