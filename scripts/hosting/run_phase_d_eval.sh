#!/usr/bin/env bash
# Phase D — run bot-bench, persist JSONL, write baseline + markdown report.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
export PYTHONPATH="${PYTHONPATH:-}:$ROOT"
export LUMEN_EVAL_DIR="${LUMEN_EVAL_DIR:-$ROOT/.lumen_eval}"
mkdir -p "$LUMEN_EVAL_DIR"

python3 - <<'PY'
import json, os
from pathlib import Path
from lumen.engine.services.evaluation import (
    run_bot_bench_suite,
    save_baseline,
    regression_check,
    render_eval_markdown,
)

eval_dir = Path(os.environ["LUMEN_EVAL_DIR"])
result = run_bot_bench_suite(work_root=eval_dir / "bench_work", persist=True)
summary = result["summary"]
save_baseline(summary, eval_dir / "baseline.json")
(eval_dir / "REPORT.md").write_text(render_eval_markdown(summary), encoding="utf-8")
(eval_dir / "last_run.json").write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
base = eval_dir / "baseline.json"
reg = regression_check(result["records"], baseline_path=base if base.is_file() else None)
print(json.dumps({"ok": result.get("ok"), "summary": summary, "regression": reg}, indent=2, ensure_ascii=False))
raise SystemExit(0 if result.get("ok") and reg.get("ok") else 1)
PY
