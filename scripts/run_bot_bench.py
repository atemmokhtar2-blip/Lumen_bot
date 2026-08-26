#!/usr/bin/env python3
"""Run Bot-bench and exit non-zero on failure (CI quality gate)."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def main() -> int:
    from lumen.engine.services.evaluation.bot_bench_runner import run_bot_bench_suite

    report = run_bot_bench_suite(persist=True)
    print(json.dumps({k: report.get(k) for k in ("ok", "passed", "failed", "total", "success_rate") if isinstance(report, dict)}, indent=2))
    if not isinstance(report, dict):
        return 1
    ok = bool(report.get("ok", report.get("passed", 0) >= report.get("total", 1)))
    # Threshold: require at least 50% unless empty
    total = int(report.get("total") or 0)
    passed = int(report.get("passed") or 0)
    if total == 0:
        print("no scenarios", file=sys.stderr)
        return 1
    rate = passed / total
    print(f"success_rate={rate:.2%}")
    min_rate = float(__import__("os").getenv("BOT_BENCH_MIN_RATE") or "0.5")
    return 0 if rate >= min_rate else 2


if __name__ == "__main__":
    raise SystemExit(main())
