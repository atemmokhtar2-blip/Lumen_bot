"""Dialogue foundation — Rasa-only production path."""
from __future__ import annotations

import os

from dialogue.runtime.registry import handle_turn, runtime_status, dialogue_runtime_enabled


def test_rasa_only_when_disabled():
    os.environ["DIALOGUE_ENABLED"] = "0"
    assert dialogue_runtime_enabled() is False
    st = runtime_status()
    assert st["active_engine"] is None
    assert st["rule_engine"] == "disabled"


def test_handle_turn_none_without_model():
    os.environ["DIALOGUE_ENABLED"] = "1"
    # no model in CI → None
    import asyncio
    resp = asyncio.run(handle_turn("مرحبا", sender_id="1", plan_id="free"))
    # Without model, must not invent rule answers
    assert resp is None or (hasattr(resp, "engine") and resp.engine == "rasa_v1")


def test_bridge_no_rules():
    os.environ["DIALOGUE_ENABLED"] = "0"
    import asyncio
    from bot_interface.dialogue_bridge import handle_dialogue
    text = asyncio.run(handle_dialogue("تمام", sender_id="1", plan_id="free"))
    assert text is None
