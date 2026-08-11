#!/usr/bin/env bash
# Train Maestro Rasa dialogue model (run in repo root).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT/dialogue"
echo "[train] working dir: $(pwd)"
if ! command -v rasa >/dev/null 2>&1; then
  echo "[train] installing rasa (this may take a few minutes)..."
  pip install -q -r "$ROOT/requirements-dialogue.txt"
fi
mkdir -p models
rasa data validate --domain domain.yml --data data || true
rasa train --domain domain.yml --config config.yml --data data --out models
echo "[train] done. Models:"
ls -la models/
