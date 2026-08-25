#!/usr/bin/env python3
"""Start B2B API for live DAST/ZAP (test isolation defaults)."""
from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

# Fail-open for local DAST host only — never production defaults
os.environ.setdefault("ENVIRONMENT", "test")
os.environ.setdefault("TBE_ENV", "test")
os.environ.setdefault("TBE_MULTI_TENANT", "0")
os.environ.setdefault("TBE_REQUIRE_DOCKER", "0")
os.environ.setdefault("TBE_ALLOW_LOCAL_PROCESS", "1")
os.environ.setdefault("PLATFORM_ADMIN_TOKEN", "dast-live-admin-token-32chars-xx")
os.environ.setdefault("STRIPE_WEBHOOK_SECRET", "whsec_dast_live_secret")
os.environ.setdefault("ALLOW_DEV_BILLING", "0")
os.environ.setdefault("API_HOST", "127.0.0.1")
os.environ.setdefault("API_PORT", "8765")
if not os.environ.get("OUTPUT_DIR"):
    import tempfile
    os.environ["OUTPUT_DIR"] = tempfile.mkdtemp(prefix="dast-api-out-")

from api.app import run_api

if __name__ == "__main__":
    run_api(host=os.environ["API_HOST"], port=int(os.environ["API_PORT"]))
