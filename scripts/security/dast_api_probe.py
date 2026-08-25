#!/usr/bin/env python3
"""DAST-style API probe — aggressive unauthenticated + cross-tenant checks.

Usage (server already running optional; default: in-process TestClient):
  PYTHONPATH=. python scripts/security/dast_api_probe.py

Exit 0 only if all probes fail closed (no unexpected 2xx on sensitive routes).
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


SENSITIVE = [
    "/v1/admin/credits/ten_probe/overview",
    "/v1/admin/credits/ten_probe/ledger",
    "/v1/admin/credits/ten_probe/reconcile",
    "/v1/me",
    "/v1/me/credits/overview",
    "/v1/me/credits/ledger",
    "/v1/generate",
    "/v1/hosts/start",
    "/v1/hosts/stop",
    "/v1/billing/credits/checkout",
    "/v1/billing/dev/activate",
    "/v1/me/rotate_key",
]


async def run() -> int:
    os.environ.setdefault("ENVIRONMENT", "test")
    os.environ.setdefault("TBE_ENV", "test")
    os.environ["OUTPUT_DIR"] = tempfile.mkdtemp(prefix="dast-out-")
    os.environ["PLATFORM_ADMIN_TOKEN"] = "dast-probe-admin-token-32chars-xx"
    os.environ.setdefault("TBE_MULTI_TENANT", "0")
    os.environ.setdefault("TBE_REQUIRE_DOCKER", "0")
    os.environ.setdefault("TBE_ALLOW_LOCAL_PROCESS", "1")
    os.environ["STRIPE_WEBHOOK_SECRET"] = "whsec_dast_probe"

    import b2b_platform.tenants as tmod
    tmod._STORE = None
    try:
        from b2b_platform.credits.service import reset_credit_service_for_tests
        reset_credit_service_for_tests()
    except Exception:
        pass

    from aiohttp.test_utils import TestClient, TestServer
    from api.app import create_app
    from b2b_platform.tenants import get_tenant_store

    store = get_tenant_store()
    ten_a, key_a = store.create("DastA")
    ten_b, key_b = store.create("DastB")

    failures = []
    app = create_app()
    async with TestClient(TestServer(app)) as client:
        # 1) Unauthenticated sensitive routes
        for path in SENSITIVE:
            for method in ("GET", "POST", "PUT", "DELETE"):
                r = await client.request(method, path)
                if 200 <= r.status < 300:
                    failures.append(f"unauth_success {method} {path} -> {r.status}")

        # 2) Cross-tenant admin with tenant key
        r = await client.get(
            f"/v1/admin/credits/{ten_b.tenant_id}/overview",
            headers={"Authorization": f"Bearer {key_a}"},
        )
        if 200 <= r.status < 300:
            failures.append(f"idor_admin_with_tenant_key -> {r.status}")

        # 3) Forged stripe webhook
        r = await client.post(
            "/v1/billing/webhook/stripe",
            data=b'{"type":"checkout.session.completed","data":{"object":{"metadata":{"credits_amount":"99999","product_type":"credits","tenant_id":"'
            + ten_a.tenant_id.encode()
            + b'"}}}}',
            headers={"Content-Type": "application/json", "Stripe-Signature": "t=1,v1=00"},
        )
        if 200 <= r.status < 300:
            failures.append(f"forged_stripe_webhook -> {r.status}")

        # 4) Injection path params
        for p in ("../admin", "1 OR 1=1", "<script>"):
            r = await client.get(
                f"/v1/jobs/{p}",
                headers={"Authorization": f"Bearer {key_a}"},
            )
            if r.status == 200:
                failures.append(f"injection_job_id {p} -> 200")

        # 5) Legitimate self /me must work
        r = await client.get("/v1/me", headers={"Authorization": f"Bearer {key_a}"})
        if r.status != 200:
            failures.append(f"legit_me_failed -> {r.status}")
        else:
            body = await r.json()
            if body.get("tenant", {}).get("tenant_id") != ten_a.tenant_id:
                failures.append("legit_me_wrong_tenant")

    report = {"ok": not failures, "failures": failures, "tenants": [ten_a.tenant_id, ten_b.tenant_id]}
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(run()))
