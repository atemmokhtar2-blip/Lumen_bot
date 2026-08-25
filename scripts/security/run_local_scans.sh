#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT"

echo "== security baseline (strict) =="
python scripts/security/security_baseline_check.py --strict

echo "== pip-audit =="
pip install -q pip-audit
pip-audit -r requirements.txt --progress-spinner off --desc on || true

echo "== bandit HIGH =="
pip install -q bandit
bandit -r lumen.platform api lumen.engine/security \
  lumen.engine/services/tool_runtime lumen.engine/services/sandbox_runtime \
  lumen.bot/middlewares -lll -s B101,B601

echo "== semgrep custom =="
pip install -q semgrep
semgrep scan --config semgrep/ --error --metrics off --exclude tests --exclude sdks || true

echo "== credits + baseline tests =="
pip install -q pytest
pytest tests/test_security_baseline.py tests/test_welcome_credits.py tests/test_credits_ledger.py -q --tb=line

echo "== credits health monitor =="
PYTHONPATH=. python scripts/security/credits_health_monitor.py

echo "Done."
