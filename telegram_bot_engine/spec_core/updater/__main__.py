"""CLI: python -m telegram_bot_engine.spec_core.updater [--dry-run]"""
from __future__ import annotations

import json
import sys

from .apply import run_update


def main(argv: list[str] | None = None) -> int:
    argv = list(argv or sys.argv[1:])
    dry = "--dry-run" in argv
    result = run_update(write=not dry)
    print(json.dumps(result.to_dict(), ensure_ascii=False, indent=2)[:5000])
    return 0 if result.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
