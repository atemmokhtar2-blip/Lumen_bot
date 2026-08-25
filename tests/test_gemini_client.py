from __future__ import annotations

import json
import os
import time

from lumen.engine.services import gemini_client


class _Response:
    status_code = 200

    def raise_for_status(self):
        return None

    def json(self):
        return {
            "candidates": [
                {
                    "content": {
                        "parts": [
                            {
                                "text": json.dumps(
                                    {
                                        "answer": "أنا Lumen، والمطور هو حاتم.",
                                        "action": {
                                            "name": "",
                                            "requires_confirmation": False,
                                        },
                                        "translation": {
                                            "purpose": "tasks",
                                            "features_requested": ["task_add"],
                                            "flows": ["create_task"],
                                            "strict_spec": True,
                                            "model": "ignored-by-client",
                                            "confidence": 0.94,
                                            "clarification_needed": False,
                                            "clarification_questions": [],
                                        },
                                    },
                                    ensure_ascii=False,
                                )
                            }
                        ]
                    }
                }
            ]
        }


def main() -> None:
    old_key = os.environ.get("GEMINI_API_KEY")
    old_enabled = os.environ.get("GEMINI_ENABLED")
    old_experiment = os.environ.get("GEMINI_EXPERIMENT_MODE")
    old_model = os.environ.get("GEMINI_MODEL")
    captured = {}
    sleeps = []

    try:
        os.environ["GEMINI_API_KEY"] = "local-test-key"
        os.environ["GEMINI_ENABLED"] = "1"
        os.environ["GEMINI_EXPERIMENT_MODE"] = "1"
        os.environ["GEMINI_MODEL"] = "gemini-1.5-flash"

        original_post = gemini_client.requests.post
        original_sleep = gemini_client.time.sleep

        def fake_post(url, **kwargs):
            captured["url"] = url
            captured["payload"] = kwargs["json"]
            return _Response()

        gemini_client.requests.post = fake_post
        gemini_client.time.sleep = lambda seconds: sleeps.append(seconds)
        try:
            result = gemini_client.translate(
                "عايز أضيف مهمة للمشروع",
                {
                    "server_facts": {
                        "data_available": True,
                        "plan": {"name": "free"},
                        "remaining": {"messages": 42},
                    }
                },
            )
        finally:
            gemini_client.requests.post = original_post
            gemini_client.time.sleep = original_sleep

        assert result["source"] == "gemini"
        assert result["translation"]["features_requested"] == ["task_add"]
        assert result["translation"]["model"] == "gemini-1.5-flash"
        assert sleeps == [2]
        prompt = captured["payload"]["contents"][0]["parts"][0]["text"]
        assert "messages" in prompt and "42" in prompt
        assert captured["payload"]["generationConfig"]["responseMimeType"] == "application/json"
        print("gemini client contract/delay: OK")
    finally:
        for name, value in (
            ("GEMINI_API_KEY", old_key),
            ("GEMINI_ENABLED", old_enabled),
            ("GEMINI_EXPERIMENT_MODE", old_experiment),
            ("GEMINI_MODEL", old_model),
        ):
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value


if __name__ == "__main__":
    main()
