from __future__ import annotations

from telegram_bot_engine.services import gemini_client


def main() -> None:
    original_generate = gemini_client.generate
    calls = []

    def fake_generate(mode, text, context):
        calls.append(context)
        if len(calls) == 1:
            raise RuntimeError("Gemini HTTP 400 invalid response schema")
        return {"source": "gemini", "answer": "ok"}

    gemini_client.generate = fake_generate
    try:
        history = [{"role": "user", "content": str(i)} for i in range(6)]
        result = gemini_client.chat("ابدأ", {"conversation_history": history})
    finally:
        gemini_client.generate = original_generate
    assert result["answer"] == "ok"
    assert len(calls) == 2
    assert len(calls[1]["conversation_history"]) == 4
    assert calls[1]["compact_retry"] is True

    calls = []
    original_generate = gemini_client.generate

    def forbidden_generate(mode, text, context):
        calls.append(context)
        raise RuntimeError("Gemini HTTP 429 quota exceeded")

    gemini_client.generate = forbidden_generate
    try:
        try:
            gemini_client.chat("من انت", {})
        except RuntimeError as exc:
            assert "429" in str(exc)
        else:
            raise AssertionError("429 must propagate to key failover")
    finally:
        gemini_client.generate = original_generate
    assert len(calls) == 1
    print("gemini compact retry: OK")


if __name__ == "__main__":
    main()
