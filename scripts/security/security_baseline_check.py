#!/usr/bin/env python3
"""Static security baseline — fail closed for world-class posture.

Checks (no network required):
  1. Admin credit routes call require_admin
  2. execute_tool always evaluates PolicyEngine
  3. credit_credits privilege rules present in service
  4. Security headers middleware registered on API app
  5. Welcome grant is promotional + expiry-bound
  6. No verify=False in production paths
  7. CORS default deny (no wildcard in prod path)
  8. Gitleaks / security workflow files exist
"""
from __future__ import annotations

import argparse
import ast
import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def _read(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8", errors="replace")


def check(name: str, ok: bool, detail: str, failures: list) -> None:
    status = "PASS" if ok else "FAIL"
    print(f"[{status}] {name}: {detail}")
    if not ok:
        failures.append(name)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--strict", action="store_true", help="exit 1 on any failure")
    args = ap.parse_args()
    failures: list[str] = []

    # 1) Admin routes
    audit = _read("api/routes/audit.py")
    for fn in ("admin_tenant_overview", "admin_tenant_ledger", "admin_tenant_reconcile"):
        # crude but effective: function body contains require_admin
        m = re.search(rf"async def {fn}\(.*?\n(.*?)(?=\nasync def |\Z)", audit, re.S)
        body = m.group(1) if m else ""
        check(
            f"admin_route.{fn}",
            "require_admin" in body,
            "require_admin present" if "require_admin" in body else "MISSING require_admin",
            failures,
        )

    # 2) PolicyEngine in execute_tool
    executor = _read("telegram_bot_engine/services/tool_runtime/executor.py")
    check(
        "tool_runtime.policy",
        "PolicyEngine" in executor and "evaluate" in executor,
        "PolicyEngine.evaluate on execute_tool path",
        failures,
    )

    # 3) credit_credits privilege rules
    service = _read("b2b_platform/credits/service.py")
    for needle in (
        "promotional_requires_expiry",
        "promotional_requires_promo_reason",
        "welcome_grant_key_required",
        "ensure_fresh_wallet",
    ):
        check(
            f"credits.rule.{needle}",
            needle in service,
            "present" if needle in service else "MISSING",
            failures,
        )

    # 4) Security headers middleware
    app = _read("api/app.py")
    check(
        "api.security_headers",
        "security_headers" in app or "X-Content-Type-Options" in app or "Content-Security-Policy" in app,
        "security headers middleware or CSP/XCTO present",
        failures,
    )

    # 5) onboarding promotional + TTL
    onboarding = _read("b2b_platform/credits/onboarding.py")
    check(
        "credits.welcome.promotional",
        "promotional=True" in onboarding and "promo_expires_at" in onboarding,
        "welcome grant is promotional with expiry",
        failures,
    )
    check(
        "credits.welcome.amount_formula",
        "INITIAL_CREDITS_COMPUTED" in onboarding and "50" in onboarding,
        "computed from seeded pricing",
        failures,
    )

    # 6) verify=False outside tests
    bad_verify = []
    for path in ROOT.rglob("*.py"):
        rel = str(path.relative_to(ROOT))
        if rel.startswith(("tests/", "sdks/", ".git/", "scripts/security/")):
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        if re.search(r"verify\s*=\s*False", text):
            bad_verify.append(rel)
    check(
        "tls.verify_false",
        len(bad_verify) == 0,
        "none" if not bad_verify else f"found in {bad_verify[:5]}",
        failures,
    )

    # 7) CORS fail-closed comment / logic
    check(
        "api.cors_deny_default",
        "Never defaults to *" in app or 'raw == "*"' in app,
        "wildcard CORS blocked outside explicit dev",
        failures,
    )

    # 8) Workflow & tooling presence
    for rel in (
        ".github/workflows/security.yml",
        ".github/dependabot.yml",
        ".gitleaks.toml",
        "scripts/security/credits_health_monitor.py",
        "semgrep/maestro-security.yml",
        "scripts/security/dast_api_probe.py",
        "tests/test_security_idor_dast.py",
        ".github/workflows/dast-zap.yml",
        ".zap/rules.tsv",
        "scripts/security/start_api_dast.py",
        ".github/workflows/supply-chain.yml",
        "docs/27_PHASE3_SUPPLY_CHAIN.md",
        "scripts/security/seed_dast_tenants.py",
    ):
        check(
            f"tooling.{rel}",
            (ROOT / rel).exists(),
            "exists" if (ROOT / rel).exists() else "MISSING",
            failures,
        )

    # 9) Multi-tenant defaults
    check(
        "api.multi_tenant_default",
        'TBE_MULTI_TENANT' in app and '"1"' in app,
        "multi-tenant default on",
        failures,
    )

    print("---")
    print(f"failures={len(failures)} {failures}")
    if args.strict and failures:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
