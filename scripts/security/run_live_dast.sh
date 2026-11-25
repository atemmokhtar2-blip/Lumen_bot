#!/usr/bin/env bash
# Requires: docker (OWASP ZAP official image) + python app deps
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT"
OUT="${TMPDIR:-/tmp}/lumen-dast-$$"
mkdir -p "$OUT"
export ENVIRONMENT=test TBE_ENV=test TBE_MULTI_TENANT=0 TBE_REQUIRE_DOCKER=0
export TBE_ALLOW_LOCAL_PROCESS=1 API_HOST=127.0.0.1 API_PORT=8765 OUTPUT_DIR="$OUT/data"
export PLATFORM_ADMIN_TOKEN="${PLATFORM_ADMIN_TOKEN:-$(python -c 'import secrets; print(secrets.token_urlsafe(48))')}"
export STRIPE_WEBHOOK_SECRET="${STRIPE_WEBHOOK_SECRET:-whsec_$(python -c 'import secrets; print(secrets.token_urlsafe(32))')}"
export TBE_TOKEN_SECRET="${TBE_TOKEN_SECRET:-$(python -c 'import secrets; print(secrets.token_urlsafe(48))')}"
export TELEGRAM_BOT_TOKEN="${TELEGRAM_BOT_TOKEN:-123456:$(python -c 'import secrets; print(secrets.token_urlsafe(32))')}"
export ALLOW_DEV_BILLING=0
export DAST_BASE_URL=http://127.0.0.1:8765 DAST_SEED_FILE="$OUT/tenants.json"
ZAP_IMAGE="${ZAP_IMAGE:-ghcr.io/zaproxy/zaproxy:stable}"

python scripts/security/start_api_dast.py >"$OUT/api.log" 2>&1 &
PID=$!
cleanup() {
  kill "$PID" 2>/dev/null || true
  rm -f "$DAST_SEED_FILE" "$ROOT/zap-auth-report.json"
  rm -rf "$OUT"
}
trap cleanup EXIT
for _ in $(seq 1 40); do curl -sf "$DAST_BASE_URL/health" >/dev/null && break; sleep 0.5; done

python scripts/security/seed_dast_tenants.py
python scripts/security/live_idor_http.py

command -v docker >/dev/null || { echo "docker required for real ZAP engine"; exit 1; }
docker pull "$ZAP_IMAGE"
docker run --rm --user 0 --network host \
  -v "$ROOT:/zap/wrk:rw" -v "$ROOT/.zap:/zap/rules:ro" \
  "$ZAP_IMAGE" zap-baseline.py -t "$DAST_BASE_URL" -a \
  -c /zap/rules/rules.tsv -J /zap/wrk/zap-baseline-report.json
docker run --rm --user 0 --network host \
  -v "$ROOT:/zap/wrk:rw" -v "$ROOT/.zap:/zap/rules:ro" \
  "$ZAP_IMAGE" zap-api-scan.py -t "$DAST_BASE_URL/openapi.yaml" -f openapi -a \
  -c /zap/rules/rules.tsv -J /zap/wrk/zap-api-report.json
python scripts/security/zap_fail_on_severity.py zap-baseline-report.json
python scripts/security/zap_fail_on_severity.py zap-api-report.json
echo "Real ZAP engine finished."
