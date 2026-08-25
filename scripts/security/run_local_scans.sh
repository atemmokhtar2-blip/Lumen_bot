#!/usr/bin/env bash
# Local vulnerability monitoring — mirrors CI security workflow
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT"

echo "== pip-audit =="
pip install -q pip-audit
pip-audit -r requirements.txt --progress-spinner off --desc on || true

echo "== bandit (critical paths) =="
pip install -q bandit
bandit -r b2b_platform api telegram_bot_engine/security \
  telegram_bot_engine/services/tool_runtime telegram_bot_engine/services/sandbox_runtime \
  bot_interface/middlewares \
  -c pyproject.toml -ll -s B101,B601 || true

echo "== credits tests =="
pip install -q pytest
pytest tests/test_welcome_credits.py tests/test_credits_ledger.py -q --tb=line

echo "== credits health monitor =="
python scripts/security/credits_health_monitor.py

echo "Done."
