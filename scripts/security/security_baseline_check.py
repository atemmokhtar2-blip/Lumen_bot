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
    audit = _read("lumen/api/routes/audit.py")
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
    executor = _read("lumen/engine/services/tool_runtime/executor.py")
    check(
        "tool_runtime.policy",
        "PolicyEngine" in executor and "evaluate" in executor,
        "PolicyEngine.evaluate on execute_tool path",
        failures,
    )

    # 3) credit_credits privilege rules
    service = _read("lumen/platform/credits/service.py")
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
    app = _read("lumen/api/app.py")
    check(
        "api.security_headers",
        "security_headers" in app or "X-Content-Type-Options" in app or "Content-Security-Policy" in app,
        "security headers middleware or CSP/XCTO present",
        failures,
    )

    # 5) onboarding promotional + TTL
    onboarding = _read("lumen/platform/credits/onboarding.py")
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
        if rel.startswith(("tests/", ".git/", "scripts/security/")):
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

    # 8) Workflow & tooling presence — only paths that exist in this repo
    for rel in (
        ".github/workflows/security.yml",
        ".github/dependabot.yml",
        ".gitleaks.toml",
        "scripts/security/credits_health_monitor.py",
        "scripts/security/dast_api_probe.py",
        "tests/test_security_idor_dast.py",
        ".github/workflows/dast-zap.yml",
        "scripts/security/start_api_dast.py",
        ".github/workflows/supply-chain.yml",
        ".github/workflows/policy-as-code.yml",
        "scripts/security/seed_dast_tenants.py",
        "lumen/api/openapi.yaml",
        "docs/11-security.md",
    ):
        check(
            f"tooling.{rel}",
            (ROOT / rel).exists(),
            "exists" if (ROOT / rel).exists() else "MISSING",
            failures,
        )

    # 9) Multi-tenant defaults (isolation policy — not only app.py)
    isolation = _read("lumen/engine/services/isolation_policy.py")
    multi_ok = (
        ('TBE_MULTI_TENANT' in isolation and '"1"' in isolation)
        or ("TBE_MULTI_TENANT" in app)
    )
    check(
        "api.multi_tenant_default",
        multi_ok,
        "multi-tenant default on",
        failures,
    )


    # Phase D — permanent host / Firecracker production path
    select_src = _read("lumen/engine/services/sandbox_runtime/select.py")
    check(
        "sandbox.production_firecracker_only",
        "is_production_sandbox_path" in select_src and "firecracker" in select_src.lower(),
        "select_sandbox_backend production path is Firecracker-only",
        failures,
    )
    host_src = _read("lumen/engine/services/hosting/service.py")
    check(
        "hosting.permanent_firecracker_gate",
        "Firecracker" in host_src and "select_sandbox_backend" in host_src,
        "HostService enforces Firecracker for permanent host",
        failures,
    )
    gate_src = _read("lumen/platform/prod_security_gate.py")
    check(
        "prod_gate.sandbox_backend",
        "assert_production_sandbox_backend" in gate_src,
        "boot gate refuses docker/gvisor sandbox in production",
        failures,
    )
    waf = _read("lumen/api/edge_waf.py")
    app_src = _read("lumen/api/app.py")
    check(
        "edge_waf.middleware_registered",
        "edge_waf_middleware" in app_src and "CF-Ray" in waf,
        "Edge WAF middleware registered on API app",
        failures,
    )
    sec_yml = _read(".github/workflows/security.yml")
    # HIGH gate must not soft-pass with || true on the -lll line
    high_line = [ln for ln in sec_yml.splitlines() if "bandit" in ln and "-lll" in ln]
    high_ok = bool(high_line) and all("|| true" not in ln for ln in high_line)
    check(
        "ci.bandit_no_soft_pass_high",
        high_ok,
        "Bandit HIGH (-lll) gate has no || true",
        failures,
    )
    lock = (ROOT / "requirements.lock").exists() and (ROOT / "requirements.txt").exists()
    check(
        "supply.requirements_lock",
        lock,
        "requirements.lock present for pinned production installs",
        failures,
    )
    # Phase D lock sync + WAF secret dual-ACK + isolated docker ACK strings in code
    check(
        "supply.assert_lockfile_script",
        (ROOT / "scripts/security/assert_lockfile.py").exists(),
        "assert_lockfile.py exists",
        failures,
    )
    gate = _read("lumen/platform/prod_security_gate.py")
    check(
        "prod_gate.docker_isolation_ack",
        "I_ACCEPT_ISOLATED_DOCKER_NOT_FIRECRACKER" in gate
        or "I_ACCEPT_ISOLATED_DOCKER_NOT_FIRECRACKER" in _read("lumen/engine/services/sandbox_runtime/select.py"),
        "isolated docker dual-ACK string present",
        failures,
    )
    waf = _read("lumen/api/edge_waf.py")
    check(
        "edge_waf.secret_not_cf_ray_alone",
        "TBE_EDGE_WAF_SECRET" in waf and "compare_digest" in waf,
        "WAF requires shared secret (not CF-Ray alone)",
        failures,
    )

    # Phase E — monitoring + pen suite presence
    check(
        "phase_e.security_alerts",
        (ROOT / "lumen/platform/security_alerts.py").exists(),
        "security_alerts module present",
        failures,
    )
    check(
        "phase_e.pen_tests",
        (ROOT / "tests/test_phase_e_monitoring_pen.py").exists(),
        "Phase E penetration test suite present",
        failures,
    )
    check(
        "phase_e.weekly_review_workflow",
        (ROOT / ".github/workflows/security-review-weekly.yml").exists(),
        "weekly security review workflow present",
        failures,
    )
    se = _read("lumen/platform/security_events.py")
    check(
        "phase_e.emit_dispatches_alerts_metrics",
        "dispatch_alert" in se,
        "security_events.emit dispatches alerts",
        failures,
    )
    check(
        "phase_e.metrics_module",
        (ROOT / "lumen/platform/security_metrics.py").exists(),
        "security_metrics module",
        failures,
    )
    check(
        "phase_e.monitoring_hygiene_script",
        (ROOT / "scripts/security/assert_monitoring_hygiene.py").exists(),
        "assert_monitoring_hygiene.py",
        failures,
    )
    print("---")
    print(f"failures={len(failures)} {failures}")
    if args.strict and failures:
        return 1
    return 0



if __name__ == "__main__":
    raise SystemExit(main())
