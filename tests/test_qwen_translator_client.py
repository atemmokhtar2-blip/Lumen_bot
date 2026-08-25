from __future__ import annotations

import os


def main() -> None:
    os.environ["LUMEN_TRANSLATOR_ENABLED"] = "1"
    os.environ["LUMEN_TRANSLATOR_URL"] = "https://qwen.example"
    os.environ["LUMEN_TRANSLATOR_TOKEN"] = "test-service-token"
    os.environ["LUMEN_TRANSLATOR_TIMEOUT_SEC"] = "20"
    os.environ.pop("GEMINI_ENABLED", None)
    os.environ.pop("GEMINI_API_KEY", None)

    from lumen.engine.services import translator_client

    captured = {}

    class Response:
        status_code = 200

        def raise_for_status(self):
            return None

        def json(self):
            return {
                "ok": True,
                "source": "qwen",
                "model": "qwen2.5-1.5b-instruct",
                "translation": {
                    "purpose": "group moderation",
                    "features_requested": ["welcome_set", "user_ban"],
                    "flows": ["welcome", "ban"],
                    "strict_spec": True,
                    "model": "qwen2.5-1.5b-instruct",
                    "confidence": 0.9,
                    "clarification_needed": False,
                    "clarification_questions": [],
                    "spec_request": "Telegram bot for group management with welcome_set and user_ban",
                },
            }

    original_post = translator_client.requests.post

    def fake_post(url, json, headers, timeout):
        captured.update(url=url, json=json, headers=headers, timeout=timeout)
        return Response()

    translator_client.requests.post = fake_post
    try:
        result = translator_client.translate_request(
            "عايز بوت جروب يرحب بالأعضاء ويحظر اللي يشتم",
            {
                "conversation_history": [{"role": "user", "content": "جروب إدارة"}],
                "server_facts": {"plan": "free", "project": "Lumen"},
                "gemini_understanding": {
                    "purpose": "group moderation",
                    "features_requested": ["welcome_set", "user_ban"],
                    "source": "gemini",
                },
            },
        )
    finally:
        translator_client.requests.post = original_post

    assert result and result["features_requested"] == ["welcome_set", "user_ban"]
    assert captured["url"] == "https://qwen.example/v1/translate"
    assert captured["headers"]["Authorization"] == "Bearer test-service-token"
    assert captured["json"]["server_context"]["project"] == "Lumen"
    assert captured["json"]["gemini_understanding"]["source"] == "gemini"
    assert "spec_core_capabilities" in captured["json"]
    print("qwen translator client: OK")


if __name__ == "__main__":
    main()
