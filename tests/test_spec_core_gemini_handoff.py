from __future__ import annotations

import os
import shutil
from pathlib import Path

from lumen.engine import generate_bot
from lumen.engine.services.gemini_client import validate_spec_translation


def main() -> None:
    translation = {
        "purpose": "group_management",
        "features_requested": ["welcome_set", "user_ban"],
        "flows": [],
        "strict_spec": True,
        "model": "gemini-3.5-flash-lite",
        "confidence": 0.95,
        "clarification_needed": False,
        "clarification_questions": [],
        "spec_request": "Telegram bot with features: welcome_set, user_ban",
    }
    assert validate_spec_translation(translation) is True

    root = Path("/tmp/spec_core_gemini_handoff_test")
    shutil.rmtree(root, ignore_errors=True)
    root.mkdir(parents=True, exist_ok=True)
    old_output = os.environ.get("OUTPUT_DIR")
    os.environ["OUTPUT_DIR"] = str(root)
    try:
        result = generate_bot(
            translation["spec_request"],
            work_dir=root / "project",
            user_id=770002,
            preferred_keys=translation["features_requested"],
        )
        assert bool(getattr(result, "success", False)) is True
        project_path = Path(str(getattr(result, "project_path", "")))
        assert project_path.is_dir()
        assert (project_path / "main.py").is_file()
        metadata = getattr(result, "metadata", {}) or {}
        assert metadata.get("zero_ai") is True
        print("spec_core Gemini handoff: OK")
    finally:
        if old_output is None:
            os.environ.pop("OUTPUT_DIR", None)
        else:
            os.environ["OUTPUT_DIR"] = old_output


if __name__ == "__main__":
    main()
