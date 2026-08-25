#!/usr/bin/env bash
# Live DAST helper: start API, unauth matrix, optional ZAP docker
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT"
OUT="${TMPDIR:-/tmp}/maestro-dast-$$"
mkdir -p "$OUT"
export ENVIRONMENT=test TBE_ENV=test TBE_MULTI_TENANT=0 TBE_REQUIRE_DOCKER=0
export TBE_ALLOW_LOCAL_PROCESS=1 API_HOST=127.0.0.1 API_PORT=8765 OUTPUT_DIR="$OUT/data"
export PLATFORM_ADMIN_TOKEN=dast-live-admin-token-32chars-xx
export STRIPE_WEBHOOK_SECRET=whsec_dast_live_secret ALLOW_DEV_BILLING=0

python scripts/security/start_api_dast.py >"$OUT/api.log" 2>&1 &
PID=$!
trap 'kill $PID 2>/dev/null || true' EXIT

for i in $(seq 1 40); do
  curl -sf "http://127.0.0.1:8765/health" >/dev/null && break
  sleep 0.5
done
curl -sf "http://127.0.0.1:8765/health" >/dev/null

echo "== unauth matrix =="
for path in /v1/me /v1/generate /v1/admin/credits/x/overview /v1/hosts/start /v1/me/credits/overview; do
  code=$(curl -s -o /dev/null -w "%{http_code}" "http://127.0.0.1:8765$path")
  echo "$path $code"
  [[ "$code" == 2* ]] && { echo FAIL; exit 1; }
done

echo "== IDOR pytest =="
PYTHONPATH=. pytest tests/test_security_idor_dast.py -q --tb=line

if command -v docker >/dev/null 2>&1; then
  echo "== OWASP ZAP baseline (docker) =="
  docker run --rm --network host \
    -v "$ROOT/.zap:/zap/wrk:ro" \
    owasp/zap2docker-stable zap-baseline.py \
    -t http://127.0.0.1:8765 -a -c /zap/wrk/rules.tsv || true
else
  echo "docker not available — ZAP runs in GitHub Actions workflow dast-zap.yml"
fi
echo "Done."
