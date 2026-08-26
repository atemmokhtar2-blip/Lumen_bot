#!/usr/bin/env bash
# Phase B — run official Temporal worker for Lumen multi-agent workflows.
# Prereq: Temporal server (e.g. docker run temporalio/auto-setup) + pip install temporalio
set -euo pipefail
export TEMPORAL_HOST="${TEMPORAL_HOST:-localhost:7233}"
export TEMPORAL_NAMESPACE="${TEMPORAL_NAMESPACE:-default}"
export TEMPORAL_TASK_QUEUE="${TEMPORAL_TASK_QUEUE:-tbe-generate}"
export TBE_WORKFLOW_ENGINE="${TBE_WORKFLOW_ENGINE:-temporal}"
cd "$(dirname "$0")/../.."
exec python -m lumen.engine.services.multi_agent.temporal_worker
