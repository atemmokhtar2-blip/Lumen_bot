"""Phase 0 dialogue foundation — must stay green."""
from __future__ import annotations

import asyncio
import os

import pytest

from dialogue.runtime.normalize import normalize
from dialogue.runtime.rule_engine import RuleEngine, classify
from dialogue.runtime.contract import DialogueRequest
from dialogue.runtime.registry import handle_turn, runtime_status


def test_normalize_arabic_variants():
    assert normalize("أحمد") == normalize("احمد") or "احمد" in normalize("أحمد")
    assert "مرحبا" in normalize("مرحباً")


@pytest.mark.parametrize(
    "text,intent",
    [
        ("مرحبا", "greet"),
        ("السلام عليكم", "greet"),
        ("hello", "greet"),
        ("خطتي إيه", "ask_plan"),
        ("/plan", "ask_plan"),
        ("الأسعار", "ask_pricing"),
        ("ازاي أولد بوت", "ask_how_to_generate"),
        ("تقدر تعمل إيه", "ask_capabilities"),
        ("مساعدة", "ask_help"),
        ("أنت بوت؟", "bot_challenge"),
        ("باي", "goodbye"),
        ("عايز بوت متجر", "describe_bot_idea"),
        ("وصفة طبيخ", "out_of_scope"),
    ],
)
def test_classify_core_intents(text, intent):
    got, conf = classify(text)
    assert got == intent, (text, got, conf)


def test_describe_bot_idea_is_handoff():
    eng = RuleEngine()
    resp = asyncio.get_event_loop().run_until_complete(
        eng.handle(DialogueRequest(text="عايز بوت دعم عملاء", sender_id="1", plan_id="free"))
    )
    assert resp is not None
    assert resp.handled is False
    assert resp.intent == "describe_bot_idea"


def test_plan_reply_non_empty():
    eng = RuleEngine()
    resp = asyncio.get_event_loop().run_until_complete(
        eng.handle(DialogueRequest(text="خطتي", sender_id="1", plan_id="free"))
    )
    assert resp and resp.handled and "Free" in resp.text or "مجاني" in resp.text or "خطة" in resp.text


def test_handle_turn_default_runtime():
    os.environ.pop("DIALOGUE_RUNTIME", None)
    st = runtime_status()
    assert st["runtime_enabled"] is True
    assert st["rule_available"] is True

    async def _run():
        return await handle_turn("مرحبا", sender_id="42", plan_id="free")

    resp = asyncio.get_event_loop().run_until_complete(_run())
    assert resp and resp.handled and resp.text


def test_runtime_off():
    os.environ["DIALOGUE_RUNTIME"] = "0"
    try:
        resp = asyncio.get_event_loop().run_until_complete(
            handle_turn("مرحبا", sender_id="42", plan_id="free")
        )
        assert resp is None
    finally:
        os.environ["DIALOGUE_RUNTIME"] = "1"


def test_bridge_import():
    from bot_interface.dialogue_bridge import handle_dialogue, dialogue_status

    async def _run():
        return await handle_dialogue("الأسعار", sender_id="9", plan_id="free")

    text = asyncio.get_event_loop().run_until_complete(_run())
    assert text and ("8" in text or "Starter" in text or "Free" in text)
    assert "rule" in str(dialogue_status().get("active_engine", ""))


@pytest.mark.parametrize(
    "text,intent",
    [
        ("ازاي البوت بيشتغل", "how_platform_works"),
        ("ازاي المنصة بتشتغل", "how_platform_works"),
        ("how does it work", "how_platform_works"),
        ("ازاي ارقي للخطه البرو", "how_to_upgrade"),
        ("ازاي أرقى للبرو", "how_to_upgrade"),
        ("upgrade to pro", "how_to_upgrade"),
        ("الاستضافة 24/7", "ask_about_hosting"),
        ("العلامة المائية", "ask_about_watermark"),
        ("المعاينة الحية", "ask_about_preview"),
        ("خطة pro", "ask_about_growth"),
        ("الخطة المجانية فيها ايه", "ask_about_free"),
    ],
)
def test_platform_understanding_intents(text, intent):
    got, conf = classify(text)
    assert got == intent, (text, got, conf)


def test_upgrade_answer_quality():
    eng = RuleEngine()
    import asyncio
    resp = asyncio.run(eng.handle(DialogueRequest(
        text="ازاي ارقي للخطه البرو", sender_id="1", plan_id="free"
    )))
    assert resp and resp.handled
    assert "Starter" in resp.text or "Growth" in resp.text or "ترقى" in resp.text or "ترقي" in resp.text
    assert "capability7maestro7bot@gmail.com" in resp.text or "$" in resp.text


def test_how_it_works_answer():
    eng = RuleEngine()
    import asyncio
    resp = asyncio.run(eng.handle(DialogueRequest(
        text="ازاي المنصة بتشتغل", sender_id="1", plan_id="free"
    )))
    assert resp and resp.handled
    assert "توليد" in resp.text or "معاينة" in resp.text
