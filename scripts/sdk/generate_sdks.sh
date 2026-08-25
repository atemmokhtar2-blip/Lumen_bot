#!/usr/bin/env bash
# Generate B2B client SDKs from api/openapi.yaml (Python + Node.js).
# Requires: openapi-generator-cli OR npx @openapitools/openapi-generator-cli
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
SPEC="$ROOT/api/openapi.yaml"
OUT_PY="$ROOT/sdks/python"
OUT_JS="$ROOT/sdks/javascript"
mkdir -p "$OUT_PY" "$OUT_JS"

if command -v openapi-generator-cli >/dev/null 2>&1; then
  GEN=openapi-generator-cli
elif command -v npx >/dev/null 2>&1; then
  GEN="npx --yes @openapitools/openapi-generator-cli"
else
  echo "Install openapi-generator-cli or npx to generate SDKs" >&2
  exit 1
fi

$GEN generate -i "$SPEC" -g python -o "$OUT_PY" --package-name lumen_client --skip-validate-spec
$GEN generate -i "$SPEC" -g typescript-fetch -o "$OUT_JS" --skip-validate-spec
echo "SDKs written to $OUT_PY and $OUT_JS"
