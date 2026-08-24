"""Container entrypoint: load bot token from secret file, then exec user entry.

Never leave the platform expecting BOT_TOKEN only in the process environment
from the host — the file at TBE_TOKEN_FILE (default /run/secrets/bot_token)
is the source of truth when present.
"""
from __future__ import annotations

import os
import runpy
import sys


def _load_token() -> None:
    path = (os.environ.get("TBE_TOKEN_FILE") or "/run/secrets/bot_token").strip()
    if not path:
        return
    try:
        with open(path, "r", encoding="utf-8") as fh:
            tok = fh.read().strip()
    except Exception:
        return
    if not tok:
        return
    for key in (
        "TELEGRAM_BOT_TOKEN",
        "BOT_TOKEN",
        "TOKEN",
        "TG_TOKEN",
        "API_TOKEN",
        "TELEGRAM_TOKEN",
        "BOTTOKEN",
    ):
        os.environ[key] = tok


def main() -> None:
    _load_token()
    entry = (sys.argv[1] if len(sys.argv) > 1 else "main.py").strip() or "main.py"
    # Prevent path escape — entry must be a basename under /app
    entry = os.path.basename(entry)
    if entry not in {"main.py", "bot.py", "app.py", "run.py"}:
        print("invalid entry", file=sys.stderr)
        sys.exit(2)
    sys.argv = [entry]
    runpy.run_path(entry, run_name="__main__")


if __name__ == "__main__":
    main()
