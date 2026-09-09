#!/usr/bin/env bash
# Phase D — closure gate for CI path remediation (A→D).
# Fail-closed: any missing path / failed unit / dead workflow ref → exit 1.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT"
export PYTHONPATH="${PYTHONPATH:-$ROOT}"
export TELEGRAM_BOT_TOKEN="${TELEGRAM_BOT_TOKEN:-1:phase-d-local}"
export ENVIRONMENT="${ENVIRONMENT:-development}"
export TBE_TOKEN_SECRET="${TBE_TOKEN_SECRET:-unit-test-secret-key-32b-phase-d!!}"

echo "=== D0: HEAD ==="
git rev-parse --short HEAD
git status -sb

echo "=== D1: required files exist ==="
for p in \
  tests/test_security_baseline.py \
  tests/test_welcome_credits.py \
  tests/test_credits_ledger.py \
  tests/test_github_connection_durable.py \
  tests/test_live_runner_integration.py \
  lumen/api/openapi.yaml \
  lumen/platform/credits/service.py \
  .github/workflows/ci.yml \
  .github/workflows/security.yml \
  .github/workflows/dast-zap.yml \
  scripts/security/security_baseline_check.py
do
  test -f "$p" || { echo "MISSING $p"; exit 1; }
  echo "OK $p"
done

echo "=== D2: no dead product paths in workflows/config ==="
if grep -RInE 'bot_bench|test_spec_core_unit|sdks/python|sdks/javascript|[^/]api/openapi\.yaml|lumen\.platform/credits' \
  .github/workflows pyproject.toml .gitleaks.toml scripts/security tests/test_security_baseline.py 2>/dev/null \
  | grep -v 'lumen/api/openapi.yaml' | grep -v 'phase_d_verify' ; then
  echo "DEAD_PATH_REF_FOUND"
  exit 1
fi
echo "OK no dead path refs"

echo "=== D3: ci.yml must list real unit suite ==="
grep -q 'tests/test_security_baseline.py' .github/workflows/ci.yml
grep -q 'tests/test_welcome_credits.py' .github/workflows/ci.yml
grep -q 'tests/test_credits_ledger.py' .github/workflows/ci.yml
grep -q 'tests/test_github_connection_durable.py' .github/workflows/ci.yml
grep -q 'not postgres' .github/workflows/ci.yml
grep -q 'Lumen' .github/workflows/ci.yml
# unit install must not swallow errors
if grep -n 'pip install -r requirements.txt 2>/dev/null || true' .github/workflows/ci.yml; then
  echo "STRICT_INSTALL_VIOLATION in ci.yml"
  exit 1
fi
echo "OK ci.yml suite + strict install"

echo "=== D4: openapi contract ==="
grep -q '/v1/generate' lumen/api/openapi.yaml
echo "OK openapi /v1/generate"

echo "=== D5: pytest security baseline ==="
python -m pytest tests/test_security_baseline.py -q --tb=short

echo "=== D6: simulate CI unit suite ==="
python -m pytest -q --tb=short \
  tests/test_security_baseline.py \
  tests/test_welcome_credits.py \
  tests/test_credits_ledger.py \
  tests/test_github_connection_durable.py \
  tests/test_live_runner_integration.py \
  -k "not postgres and not redis_testcontainer"

echo "=== D7: static security baseline script ==="
python scripts/security/security_baseline_check.py --strict

echo "=== PHASE_D_LOCAL_GATE_OK ==="
