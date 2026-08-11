"""If DIALOGUE_TRAIN_ON_START=1 and no model, run rasa train once."""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MODELS = ROOT / "dialogue" / "models"


def main() -> int:
    if (os.getenv("DIALOGUE_TRAIN_ON_START") or "").strip().lower() not in {
        "1", "true", "yes", "on",
    }:
        return 0
    has = list(MODELS.glob("*.tar.gz")) if MODELS.is_dir() else []
    if has:
        print(f"[dialogue] model present: {has[0].name}")
        return 0
    print("[dialogue] no model — starting rasa train on host...")
    r = subprocess.call(["bash", str(ROOT / "scripts" / "train_dialogue.sh")])
    return int(r)


if __name__ == "__main__":
    raise SystemExit(main())
