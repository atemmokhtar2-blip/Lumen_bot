from __future__ import annotations

import asyncio
import os
from pathlib import Path
from tempfile import TemporaryDirectory


def main() -> None:
    os.environ["DIALOGUE_ENABLED"] = "1"
    from bot_interface.dialogue_bridge import handle_dialogue
    from dialogue.runtime.dynamic_answers import answer_for_intent

    metadata = {
        "live_context": {
            "plan": {"name_ar": "مجاني", "name": "free"},
            "usage": {
                "messages_remaining": 1997,
                "generations_remaining": 24,
                "characters_used": 41,
            },
            "project": {"fingerprint": "abc123", "packages": {}, "models": [], "plan_ids": ["free"]},
        }
    }
    answer = answer_for_intent(
        "ask_usage",
        sender_id="0",
        fallback_plan_id="free",
        metadata=metadata,
    )
    assert answer and "1997" in answer and "24" in answer and "41" in answer, answer
    assert asyncio.run(
        handle_dialogue("مرحبا", sender_id="0", plan_id="free", metadata=metadata)
    ) is None

    from dialogue.runtime.faq_engine import FaqEngine
    assert FaqEngine().available() is False

    from b2b_platform.metering import MeteringService
    with TemporaryDirectory() as root:
        service = MeteringService(Path(root))
        service.record("tenant-test", messages=1, characters=18, event="dialogue_message")
        snapshot = service.snapshot("tenant-test")
        assert snapshot["messages"] == 1
        assert snapshot["characters"] == 18
    print("dynamic dialogue: OK")


if __name__ == "__main__":
    main()
