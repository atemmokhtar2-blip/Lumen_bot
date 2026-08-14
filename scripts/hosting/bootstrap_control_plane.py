#!/usr/bin/env python3
"""Bootstrap commercial hosting control plane on a node.

Usage:
  python scripts/hosting/bootstrap_control_plane.py
"""
from __future__ import annotations

import os
import sys


def main() -> int:
    print("=== TBE commercial hosting bootstrap ===")
    required = [
        "TBE_DATABASE_URL",
        "TBE_DOCKER_NETWORK",
        "TBE_DOCKER_REGISTRY",
        "TBE_TOKEN_SECRET",
    ]
    missing = [k for k in required if not (os.environ.get(k) or "").strip()]
    if missing and not (os.environ.get("DATABASE_URL") or "").strip():
        if "TBE_DATABASE_URL" in missing:
            pass
    if not (os.environ.get("TBE_DATABASE_URL") or os.environ.get("DATABASE_URL") or "").strip():
        print("FAIL: set TBE_DATABASE_URL=postgresql://...")
        return 1
    if not (os.environ.get("TBE_DOCKER_NETWORK") or "").strip():
        print("FAIL: set TBE_DOCKER_NETWORK=tbe-egress")
        return 1
    if len((os.environ.get("TBE_TOKEN_SECRET") or "").strip()) < 32:
        print("FAIL: TBE_TOKEN_SECRET must be 32+ chars")
        return 1

    from telegram_bot_engine.services.hosting.pg_control_plane import migrate
    migrate()
    print("OK: Postgres schema")

    from telegram_bot_engine.services.hosting.network import ensure_network, telegram_egress_hint
    ok, msg = ensure_network()
    print(("OK" if ok else "FAIL") + f": network {msg}")
    if not ok:
        return 1
    print(telegram_egress_hint())

    from telegram_bot_engine.services.hosting.registry import docker_login, registry_host
    if registry_host():
        ok, msg = docker_login()
        print(("OK" if ok else "WARN") + f": registry {msg}")
    else:
        print("WARN: TBE_DOCKER_REGISTRY unset — multi-node pull will fail")

    try:
        from telegram_bot_engine.services.hosting.fleet import FleetRegistry
        summary = FleetRegistry().cluster_summary()
        print("OK: fleet", summary)
    except Exception as e:
        print("WARN: fleet", e)

    from telegram_bot_engine.services.hosting.market_gate import evaluate_market_gate
    gate = evaluate_market_gate()
    print("market_gate ok=", gate.ok)
    if not gate.ok:
        print(gate.message_ar())
        return 2
    print("=== bootstrap complete — start workers ===")
    print("python -m telegram_bot_engine.services.hosting.worker")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
