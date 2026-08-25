#!/usr/bin/env bash
# Requires: docker (OWASP ZAP official image) + python app deps
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT"
OUT="${TMPDIR:-/tmp}/lumen-dast-$$"
mkdir -p "$OUT"
export ENVIRONMENT=test TBE_ENV=test TBE_MULTI_TENANT=0 TBE_REQUIRE_DOCKER=0
export TBE_ALLOW_LOCAL_PROCESS=1 API_HOST=127.0.0.1 API_PORT=8765 OUTPUT_DIR="$OUT/data"
export PLATFORM_ADMIN_TOKEN=dast-live-admin-token-32chars-xx
export STRIPE_WEBHOOK_SECRET=whsec_dast_live_secret ALLOW_DEV_BILLING=0
export DAST_BASE_URL=http://127.0.0.1:8765 DAST_SEED_FILE="$OUT/tenants.json"
ZAP_IMAGE="${ZAP_IMAGE:-ghcr.io/zaproxy/zaproxy:stable}"

python scripts/security/start_api_dast.py >"$OUT/api.log" 2>&1 &
PID=$!
trap 'kill $PID 2>/dev/null || true' EXIT
for i in $(seq 1 40); do curl -sf "$DAST_BASE_URL/health" >/dev/null && break; sleep 0.5; done

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
python scripts/security/zap_fail_on_severity.py zap-baseline-report.json || true
python scripts/security/zap_fail_on_severity.py zap-api-report.json || true
echo "Real ZAP engine finished."
