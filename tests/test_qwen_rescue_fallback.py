from __future__ import annotations

import os


def main() -> None:
    os.environ["LUMEN_TRANSLATOR_ENABLED"] = "1"
    os.environ["LUMEN_TRANSLATOR_URL"] = "https://qwen.example"
    os.environ["LUMEN_TRANSLATOR_TOKEN"] = "test-token"

    from lumen.bot.routers import message_router
    from lumen.engine.services import translator_client

    original = translator_client.translate_request
    calls = []

    def fake_translate(text, context):
        calls.append((text, context))
        return {
            "purpose": "group moderation",
            "features_requested": ["welcome_set", "user_ban"],
            "flows": ["welcome", "ban"],
            "strict_spec": True,
            "model": "qwen2.5-1.5b-instruct",
            "confidence": 0.9,
            "clarification_needed": False,
            "clarification_questions": [],
            "spec_request": "Telegram bot for group management with welcome_set and user_ban",
        }

    translator_client.translate_request = fake_translate
    try:
        build = message_router._qwen_rescue_translation(
            "عايز اعمل بوت جروب يرحب بالأعضاء ويحظر اللي يشتم ابدأ",
            {"data_available": True},
        )
        ordinary = message_router._qwen_rescue_translation("اهلا", {})
    finally:
        translator_client.translate_request = original

    assert build and build["features_requested"] == ["welcome_set", "user_ban"]
    assert ordinary is None
    assert len(calls) == 1
    assert calls[0][1]["gemini_unavailable"] is True
    print("qwen rescue fallback: OK")


if __name__ == "__main__":
    main()
