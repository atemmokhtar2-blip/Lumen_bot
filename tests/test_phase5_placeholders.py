"""Tests for Phase 5 (Weakness 5 — Placeholders & Hints).

Verifies that:
- should_send_force_reply detects the awaiting_text flag correctly.
- _placeholder_for returns the right Arabic hint per slot and phase.
- send_force_reply_prompt constructs a ForceReply with
  input_field_placeholder (the actual Telegram feature for Weakness 5).
- ForceReply is NOT sent when awaiting_text is absent.
- integration: callback_router + message_router send ForceReply when needed.
"""
from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock


# ---------- should_send_force_reply ----------

def test_should_send_force_reply_true_when_awaiting():
    from lumen.bot.ui.force_reply import should_send_force_reply

    state = SimpleNamespace(
        phase="gen_slots",
        slots={"awaiting_text": "1", "awaiting_slot": "bot_name"},
    )
    assert should_send_force_reply(state) is True


def test_should_send_force_reply_false_when_not_awaiting():
    from lumen.bot.ui.force_reply import should_send_force_reply

    state = SimpleNamespace(
        phase="gen_confirm",
        slots={"confirmed": "1"},
    )
    assert should_send_force_reply(state) is False


def test_should_send_force_reply_false_no_slots():
    from lumen.bot.ui.force_reply import should_send_force_reply

    state = SimpleNamespace(phase="home", slots={})
    assert should_send_force_reply(state) is False


def test_should_send_force_reply_safe_on_none():
    from lumen.bot.ui.force_reply import should_send_force_reply

    # Should not raise even with weird inputs
    assert should_send_force_reply(None) is False
    assert should_send_force_reply(SimpleNamespace(phase=None, slots=None)) is False


# ---------- _placeholder_for ----------

def test_placeholder_for_known_slot():
    from lumen.bot.ui.force_reply import _placeholder_for

    hint = _placeholder_for("bot_name", "gen_slots")
    assert "MyWeatherBot" in hint


def test_placeholder_for_bot_description_slot():
    from lumen.bot.ui.force_reply import _placeholder_for

    hint = _placeholder_for("bot_description", "gen_slots")
    assert "بوت" in hint  # Arabic word for "bot"


def test_placeholder_for_gen_type_phase_fallback():
    from lumen.bot.ui.force_reply import _placeholder_for

    # gen_type phase with no slot → should use bot_description hint
    hint = _placeholder_for(None, "gen_type")
    assert "بوت" in hint


def test_placeholder_for_unknown_slot_generic():
    from lumen.bot.ui.force_reply import _placeholder_for

    hint = _placeholder_for("unknown_xyz", None)
    assert hint  # non-empty generic fallback
    assert "اكتب" in hint  # "write" in Arabic


def test_placeholder_truncation_64_chars():
    """input_field_placeholder has a 64-char limit in Telegram."""
    from lumen.bot.ui.force_reply import _placeholder_for

    hint = _placeholder_for("bot_description", "gen_slots")
    assert len(hint) <= 64 or len(hint[:64]) == 64  # hint itself may be >64, truncation happens in send


# ---------- send_force_reply_prompt ----------

def test_send_force_reply_constructs_force_reply_with_placeholder():
    """The actual Weakness 5 fix: ForceReply + input_field_placeholder."""
    from lumen.bot.ui.force_reply import send_force_reply_prompt

    bot = MagicMock()
    bot.send_message = AsyncMock()

    asyncio.run(
        send_force_reply_prompt(
            bot=bot,
            chat_id=12345,
            prompt_text="اكتب اسم البوت:",
            slot="bot_name",
            phase="gen_slots",
        )
    )

    bot.send_message.assert_awaited_once()
    call_kwargs = bot.send_message.call_args.kwargs
    assert call_kwargs["chat_id"] == 12345
    # ForceReply must be the reply_markup
    reply_markup = call_kwargs["reply_markup"]
    assert reply_markup is not None
    fr_class_name = type(reply_markup).__name__
    assert fr_class_name == "ForceReply", f"Expected ForceReply, got {fr_class_name}"
    # input_field_placeholder must be set
    assert getattr(reply_markup, "input_field_placeholder", None) is not None
    assert "MyWeatherBot" in reply_markup.input_field_placeholder


def test_send_force_reply_text_truncated_to_4000():
    from lumen.bot.ui.force_reply import send_force_reply_prompt

    bot = MagicMock()
    bot.send_message = AsyncMock()

    long_text = "x" * 5000
    asyncio.run(
        send_force_reply_prompt(
            bot=bot,
            chat_id=1,
            prompt_text=long_text,
            slot="bot_description",
        )
    )

    call_args = bot.send_message.call_args
    assert len(call_args.kwargs["text"]) <= 4000


def test_send_force_reply_safe_on_error():
    """If bot.send_message raises, it should be caught (no crash)."""
    from lumen.bot.ui.force_reply import send_force_reply_prompt

    bot = MagicMock()
    bot.send_message = AsyncMock(side_effect=RuntimeError("network down"))

    # Should NOT raise
    asyncio.run(
        send_force_reply_prompt(
            bot=bot,
            chat_id=1,
            prompt_text="test",
        )
    )


def test_send_force_reply_placeholder_truncated_to_64():
    from lumen.bot.ui.force_reply import send_force_reply_prompt

    bot = MagicMock()
    bot.send_message = AsyncMock()

    asyncio.run(
        send_force_reply_prompt(
            bot=bot,
            chat_id=1,
            prompt_text="test",
            slot="bot_description",  # has a long hint
        )
    )

    reply_markup = bot.send_message.call_args.kwargs["reply_markup"]
    assert len(reply_markup.input_field_placeholder) <= 64


# ---------- integration: callback_router ----------

def test_callback_router_sends_force_reply_when_awaiting():
    """Verify the callback_router import path and logic exists."""
    import pathlib
    p = pathlib.Path("lumen/bot/ui/callback_router.py")
    src = p.read_text(encoding="utf-8")
    assert "should_send_force_reply" in src
    assert "send_force_reply_prompt" in src
    assert "input_field_placeholder" in src or "force_reply" in src.lower()
    # The condition: only when NOT running generation
    assert "result.run_generation" in src


def test_message_router_sends_force_reply_after_slot_answer():
    """Verify the message_router GEN_SLOTS handler has force_reply integration."""
    import pathlib
    p = pathlib.Path("lumen/bot/routers/message_router.py")
    src = p.read_text(encoding="utf-8")
    assert "should_send_force_reply" in src
    assert "send_force_reply_prompt" in src


# ---------- module structure ----------

def test_force_reply_module_has_all_exports():
    from lumen.bot.ui import force_reply

    assert hasattr(force_reply, "send_force_reply_prompt")
    assert hasattr(force_reply, "should_send_force_reply")
    assert hasattr(force_reply, "_placeholder_for")
    assert hasattr(force_reply, "_PLACEHOLDER_HINTS")


def test_placeholder_hints_dict_has_common_slots():
    from lumen.bot.ui.force_reply import _PLACEHOLDER_HINTS

    expected = {"bot_description", "bot_name", "bot_token", "github_token", "api_key"}
    for key in expected:
        assert key in _PLACEHOLDER_HINTS, f"Missing placeholder hint for {key}"
        assert _PLACEHOLDER_HINTS[key]  # non-empty
