from __future__ import annotations

import json
import os

from lumen.engine.services import gemini_client


class _Response:
    def __init__(self, status_code: int):
        self.status_code = status_code
        self.text = "unauthorized" if status_code in {401, 403} else "ok"

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
                                        "action": {"name": "", "requires_confirmation": False},
                                        "translation": {
                                            "purpose": "",
                                            "features_requested": [],
                                            "flows": [],
                                            "strict_spec": False,
                                            "model": "ignored",
                                            "confidence": 0.9,
                                            "clarification_needed": False,
                                            "clarification_questions": [],
                                            "spec_request": "",
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
    names = (
        "GEMINI_API_KEY",
        "GEMINI_API_KEY_1",
        "GEMINI_API_KEY_2",
        "GEMINI_API_KEY_3",
        "GEMINI_API_KEY_20",
        "GEMINI_API_KEY_150",
        "GEMINI_ENABLED",
        "GEMINI_MODEL",
        "GEMINI_KEY_FAILOVER_ENABLED",
        "GEMINI_KEY_COOLDOWN_SEC",
        "GEMINI_EXPERIMENT_MODE",
        "ENVIRONMENT",
    )
    old = {name: os.environ.get(name) for name in names}
    calls = []
    gemini_client._KEY_COOLDOWN_UNTIL.clear()
    try:
        os.environ.pop("GEMINI_API_KEY", None)
        os.environ["GEMINI_API_KEY_1"] = "first-key-for-test"
        os.environ["GEMINI_API_KEY_2"] = "second-key-for-test"
        for idx in range(3, 21):
            os.environ[f"GEMINI_API_KEY_{idx}"] = f"pool-key-for-test-{idx}"
        os.environ["GEMINI_API_KEY_150"] = "last-key-for-test"
        os.environ["GEMINI_ENABLED"] = "1"
        os.environ["GEMINI_MODEL"] = "gemini-3.5-flash-lite"
        os.environ["GEMINI_KEY_FAILOVER_ENABLED"] = "1"
        os.environ["GEMINI_KEY_COOLDOWN_SEC"] = "60"
        original_post = gemini_client.requests.post

        def fake_post(url, **kwargs):
            key = kwargs["params"]["key"]
            calls.append(key)
            if key == "first-key-for-test":
                return _Response(403)
            return _Response(200)

        gemini_client.requests.post = fake_post
        try:
            result = gemini_client.chat("من انت", {})
        finally:
            gemini_client.requests.post = original_post
        assert result["source"] == "gemini"
        assert calls == ["first-key-for-test", "second-key-for-test"]
        assert gemini_client._KEY_COOLDOWN_UNTIL.get("GEMINI_API_KEY_1", 0) > 0
        sources = [source for source, _ in gemini_client._api_keys()]
        assert sources[0] == "GEMINI_API_KEY_1"
        assert "GEMINI_API_KEY_20" in sources
        assert sources[-1] == "GEMINI_API_KEY_150"
        snapshot = gemini_client.status_snapshot()
        assert snapshot["key_count"] == 21
        assert "first-key-for-test" not in str(snapshot)
        assert "second-key-for-test" not in str(snapshot)

        sleep_calls = []
        original_sleep = gemini_client.time.sleep
        gemini_client.time.sleep = lambda seconds: sleep_calls.append(seconds)
        try:
            os.environ["GEMINI_EXPERIMENT_MODE"] = "1"
            os.environ["ENVIRONMENT"] = "production"
            gemini_client._experiment_delay()
            assert sleep_calls == []
            os.environ["ENVIRONMENT"] = "dev"
            gemini_client._experiment_delay()
            assert sleep_calls == [2]
        finally:
            gemini_client.time.sleep = original_sleep
        print("gemini key failover: OK")
    finally:
        gemini_client._KEY_COOLDOWN_UNTIL.clear()
        for name, value in old.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value


if __name__ == "__main__":
    main()
