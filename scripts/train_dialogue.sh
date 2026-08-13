#!/usr/bin/env bash
# Train Rasa model on this machine / hosting. Run from repo root or any cwd.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
export PIP_DISABLE_PIP_VERSION_CHECK=1
echo "[train] root=$ROOT"
python -m pip install -q -r requirements-dialogue.txt
cd "$ROOT/dialogue"
mkdir -p models
echo "[train] validating data..."
rasa data validate --domain domain.yml --data data || true
echo "[train] training model (may take several minutes)..."
rasa train --domain domain.yml --config config.yml --data data --out models --fixed-model-name maestro-dialogue
echo "[train] models:"
ls -lah models/
echo "[train] DONE — set DIALOGUE_ENABLED=1 and restart the bot process"
