"""If DIALOGUE_TRAIN_ON_START=1 and no model, attempt rasa train once.

Never aborts the bot process — train failure only logs and continues.
"""
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
    MODELS.mkdir(parents=True, exist_ok=True)
    has = list(MODELS.glob("*.tar.gz"))
    if has:
        print(f"[dialogue] model present: {has[0].name}", flush=True)
        return 0
    print("[dialogue] no model — attempting rasa train (non-fatal if it fails)...", flush=True)
    try:
        r = subprocess.call(
            ["bash", str(ROOT / "scripts" / "train_dialogue.sh")],
            cwd=str(ROOT),
        )
        if r != 0:
            print(f"[dialogue] train exited {r} — bot continues without dialogue model", flush=True)
        return 0  # always 0 so hosting does not crash
    except Exception as exc:
        print(f"[dialogue] train skipped: {type(exc).__name__}: {exc}", flush=True)
        return 0


if __name__ == "__main__":
    # When run as a CLI intentionally, still don't hard-fail CI/host boot wrappers
    code = main()
    sys.exit(code)
