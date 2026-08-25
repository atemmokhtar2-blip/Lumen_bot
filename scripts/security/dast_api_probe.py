#!/usr/bin/env python3
"""World-class in-process DAST probe — full sensitive matrix + IDOR bait.

Exit 0 only if every probe fails closed.
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
import tempfile
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

TENANT_GET = [
    "/v1/me", "/v1/me/credits/overview", "/v1/me/credits/ledger",
    "/v1/me/credits/reconcile", "/v1/jobs", "/v1/hosts", "/v1/usage",
    "/v1/billing/balance", "/v1/invoices", "/v1/dashboard",
]
TENANT_POST = [
    "/v1/me/rotate_key", "/v1/generate", "/v1/hosts/start", "/v1/hosts/stop",
    "/v1/billing/checkout", "/v1/billing/credits/checkout",
    "/v1/billing/dev/activate", "/v1/invoices",
]
ADMIN_TMPL = [
    "/v1/admin/credits/{tid}/overview",
    "/v1/admin/credits/{tid}/ledger",
    "/v1/admin/credits/{tid}/reconcile",
]


async def run() -> int:
    os.environ["ENVIRONMENT"] = "test"
    os.environ["TBE_ENV"] = "test"
    os.environ["OUTPUT_DIR"] = tempfile.mkdtemp(prefix="dast-wc-")
    os.environ["PLATFORM_ADMIN_TOKEN"] = "dast-wc-admin-token-32chars-xxxx"
    os.environ["TBE_MULTI_TENANT"] = "0"
    os.environ["TBE_REQUIRE_DOCKER"] = "0"
    os.environ["TBE_ALLOW_LOCAL_PROCESS"] = "1"
    os.environ["STRIPE_WEBHOOK_SECRET"] = "whsec_dast_wc"
    os.environ["ALLOW_DEV_BILLING"] = "0"

    import b2b_platform.tenants as tmod
    import b2b_platform.credits.service as cmod
    import b2b_platform.jobs as jmod

    tmod._STORE = None
    cmod._SVC = None
    jmod._RUNNER = None
    jmod._HANDLERS_READY = False

    from aiohttp.test_utils import TestClient, TestServer
    from api.app import create_app
    from b2b_platform.tenants import get_tenant_store
    from b2b_platform.jobs import Job, get_job_runner

    store = get_tenant_store()
    ten_a, key_a = store.create("DastWCA")
    ten_b, key_b = store.create("DastWCB")
    runner = get_job_runner()
    planted = Job(
        job_id=f"job_{uuid.uuid4().hex[:16]}",
        tenant_id=ten_a.tenant_id,
        kind="generate",
        input={"description": "secret"},
        message="bait",
    )
    runner.store.create(planted)

    failures: list[str] = []
    app = create_app()
    async with TestClient(TestServer(app)) as client:
        for path in TENANT_GET + TENANT_POST:
            for method in ("GET", "POST", "PUT", "DELETE"):
                r = await client.request(method, path)
                if 200 <= r.status < 300:
                    failures.append(f"unauth_2xx {method} {path} -> {r.status}")

        for tmpl in ADMIN_TMPL:
            r = await client.get(
                tmpl.format(tid=ten_b.tenant_id),
                headers={"Authorization": f"Bearer {key_a}", "X-Admin-Token": key_a},
            )
            if 200 <= r.status < 300:
                failures.append(f"idor_admin {tmpl} -> {r.status}")

        r = await client.get(
            f"/v1/jobs/{planted.job_id}",
            headers={"Authorization": f"Bearer {key_b}"},
        )
        if r.status == 200:
            failures.append("idor_job_visible_to_other_tenant")

        r = await client.post(
            "/v1/billing/webhook/stripe",
            data=b'{"type":"checkout.session.completed","data":{"object":{"metadata":{"credits_amount":"999999","product_type":"credits","tenant_id":"'
            + ten_a.tenant_id.encode()
            + b'"}}}}',
            headers={"Content-Type": "application/json", "Stripe-Signature": "t=1,v1=00"},
        )
        if 200 <= r.status < 300:
            failures.append(f"forged_stripe -> {r.status}")

        r = await client.get("/v1/me", headers={"Authorization": f"Bearer {key_a}"})
        if r.status != 200:
            failures.append(f"legit_me_failed -> {r.status}")
        else:
            body = await r.json()
            if body.get("tenant", {}).get("tenant_id") != ten_a.tenant_id:
                failures.append("legit_me_wrong_tenant")
            if ten_b.tenant_id in json.dumps(body):
                failures.append("legit_me_leaks_other_tenant")

    report = {
        "ok": not failures,
        "failures": failures,
        "tenants": [ten_a.tenant_id, ten_b.tenant_id],
        "planted_job": planted.job_id,
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(run()))
