from __future__ import annotations

import os


def _body():
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


class Response:
    def __init__(self, status: int):
        self.status_code = status

    def raise_for_status(self):
        if self.status_code >= 400:
            import requests
            raise requests.exceptions.HTTPError(f"status={self.status_code}")

    def json(self):
        return _body()


def main() -> None:
    os.environ["MAESTRO_TRANSLATOR_ENABLED"] = "1"
    os.environ["MAESTRO_TRANSLATOR_URL"] = "https://qwen.example"
    os.environ["MAESTRO_TRANSLATOR_TOKEN"] = "test-token"
    os.environ["MAESTRO_TRANSLATOR_RETRY_COUNT"] = "1"
    os.environ["MAESTRO_TRANSLATOR_TIMEOUT_SEC"] = "120"

    from telegram_bot_engine.services import translator_client

    original_post = translator_client.requests.post
    calls = []

    def fake_post(url, json, headers, timeout):
        calls.append(timeout)
        return Response(502 if len(calls) == 1 else 200)

    translator_client.requests.post = fake_post
    try:
        result = translator_client.translate_request("عايز بوت جروب يرحب بالأعضاء ويحظر اللي يشتم")
    finally:
        translator_client.requests.post = original_post

    assert result and len(calls) == 2
    assert calls[0] == (15.0, 120.0)
    print("qwen timeout retry: OK")


if __name__ == "__main__":
    main()
