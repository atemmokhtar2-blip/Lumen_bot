"""IDOR + DAST-grade API attack suite.

Strength requirements:
- Two real tenants with real API keys
- Cross-tenant reads/writes must fail closed
- Tenant must never act as admin
- Webhook forgery rejected
- Method/path/body fuzzing must not 500-leak or authorize
"""
from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path
from typing import Any, Callable, Awaitable

import pytest

ADMIN = "idor-dast-admin-token-value-32b-xx"


def _reset_stores(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ENVIRONMENT", "test")
    monkeypatch.setenv("TBE_ENV", "test")
    monkeypatch.setenv("OUTPUT_DIR", str(tmp_path / "out"))
    monkeypatch.setenv("PLATFORM_ADMIN_TOKEN", ADMIN)
    monkeypatch.setenv("TBE_MULTI_TENANT", "0")
    monkeypatch.setenv("TBE_REQUIRE_DOCKER", "0")
    monkeypatch.setenv("TBE_ALLOW_LOCAL_PROCESS", "1")
    monkeypatch.setenv("STRIPE_WEBHOOK_SECRET", "whsec_test_secret_for_idor_dast")
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("POSTGRES_URL", raising=False)

    import b2b_platform.tenants as tenants_mod
    import b2b_platform.credits.service as credits_mod

    tenants_mod._STORE = None
    try:
        credits_mod.reset_credit_service_for_tests()
    except Exception:
        credits_mod._SVC = None  # type: ignore[attr-defined]


async def _client_call(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    fn: Callable[[Any, str, str, str, str], Awaitable[None]],
) -> None:
    _reset_stores(tmp_path, monkeypatch)
    from aiohttp.test_utils import TestClient, TestServer
    from api.app import create_app
    from b2b_platform.tenants import get_tenant_store

    store = get_tenant_store()
    ten_a, key_a = store.create("TenantA")
    ten_b, key_b = store.create("TenantB")
    assert ten_a.tenant_id != ten_b.tenant_id

    app = create_app()
    async with TestClient(TestServer(app)) as client:
        await fn(client, ten_a.tenant_id, key_a, ten_b.tenant_id, key_b)


def test_idor_tenant_a_cannot_read_tenant_b_via_admin_path(monkeypatch, tmp_path):
    async def body(client, tid_a, key_a, tid_b, key_b):
        # Tenant key is not admin — must not open B's admin overview
        r = await client.get(
            f"/v1/admin/credits/{tid_b}/overview",
            headers={"Authorization": f"Bearer {key_a}"},
        )
        assert r.status in (401, 403)
        # Even with both headers, wrong admin token fails
        r2 = await client.get(
            f"/v1/admin/credits/{tid_b}/overview",
            headers={
                "Authorization": f"Bearer {key_a}",
                "X-Admin-Token": key_a,
            },
        )
        assert r2.status in (401, 403)

    asyncio.run(_client_call(monkeypatch, tmp_path, body))


def test_idor_me_returns_only_self(monkeypatch, tmp_path):
    async def body(client, tid_a, key_a, tid_b, key_b):
        ra = await client.get("/v1/me", headers={"Authorization": f"Bearer {key_a}"})
        rb = await client.get("/v1/me", headers={"Authorization": f"Bearer {key_b}"})
        assert ra.status == 200 and rb.status == 200
        ja, jb = await ra.json(), await rb.json()
        assert ja["tenant"]["tenant_id"] == tid_a
        assert jb["tenant"]["tenant_id"] == tid_b
        assert ja["tenant"]["tenant_id"] != jb["tenant"]["tenant_id"]

    asyncio.run(_client_call(monkeypatch, tmp_path, body))


def test_idor_credits_overview_isolated(monkeypatch, tmp_path):
    async def body(client, tid_a, key_a, tid_b, key_b):
        from b2b_platform.credits import get_credit_service

        svc = get_credit_service()
        # Fund A with paid credits so balances differ
        svc.credit_credits(tid_a, 777, reason="purchase", idempotency_key="idor-fund-a-0001")
        svc.credit_credits(tid_b, 11, reason="purchase", idempotency_key="idor-fund-b-0001")

        ra = await client.get(
            "/v1/me/credits/overview",
            headers={"Authorization": f"Bearer {key_a}"},
        )
        rb = await client.get(
            "/v1/me/credits/overview",
            headers={"Authorization": f"Bearer {key_b}"},
        )
        assert ra.status == 200 and rb.status == 200
        ja, jb = await ra.json(), await rb.json()
        bal_a = int(ja.get("wallet", {}).get("current_balance") or ja.get("current_balance") or 0)
        bal_b = int(jb.get("wallet", {}).get("current_balance") or jb.get("current_balance") or 0)
        # Welcome grant may add 400 each; paid top-up must still differ
        assert bal_a != bal_b
        # A must not see B's exact paid-only marker if isolation holds
        assert bal_a >= 777

    asyncio.run(_client_call(monkeypatch, tmp_path, body))


def test_idor_admin_with_real_token_can_read_both(monkeypatch, tmp_path):
    async def body(client, tid_a, key_a, tid_b, key_b):
        for tid in (tid_a, tid_b):
            r = await client.get(
                f"/v1/admin/credits/{tid}/overview",
                headers={"X-Admin-Token": ADMIN},
            )
            assert r.status == 200, await r.text()

    asyncio.run(_client_call(monkeypatch, tmp_path, body))


def test_idor_sandbox_paths_not_shared():
    from api.security import tenant_sandbox_root

    a = tenant_sandbox_root("ten_aaa")
    b = tenant_sandbox_root("ten_bbb")
    assert a.resolve() != b.resolve()
    assert "ten_aaa" in str(a) or a != b


def test_dast_stripe_webhook_forged_rejected(monkeypatch, tmp_path):
    async def body(client, tid_a, key_a, tid_b, key_b):
        # No signature
        r = await client.post(
            "/v1/billing/webhook/stripe",
            data=b'{"type":"checkout.session.completed","data":{"object":{}}}',
            headers={"Content-Type": "application/json"},
        )
        assert r.status in (400, 401, 403)
        # Garbage signature
        r2 = await client.post(
            "/v1/billing/webhook/stripe",
            data=b'{"type":"checkout.session.completed"}',
            headers={
                "Content-Type": "application/json",
                "Stripe-Signature": "t=1,v1=deadbeef",
            },
        )
        assert r2.status in (400, 401, 403)

    asyncio.run(_client_call(monkeypatch, tmp_path, body))


def test_dast_method_fuzz_sensitive_routes(monkeypatch, tmp_path):
    async def body(client, tid_a, key_a, tid_b, key_b):
        paths = [
            "/v1/admin/credits/ten_x/overview",
            "/v1/me/credits/ledger",
            "/v1/generate",
            "/v1/hosts/start",
            "/v1/billing/credits/checkout",
        ]
        methods = ("GET", "POST", "PUT", "PATCH", "DELETE")
        for path in paths:
            for method in methods:
                r = await client.request(method, path)
                # Unauthenticated must never be success for these
                if path.startswith("/v1/admin") or path in {
                    "/v1/me/credits/ledger",
                    "/v1/generate",
                    "/v1/hosts/start",
                    "/v1/billing/credits/checkout",
                }:
                    assert r.status in (401, 403, 404, 405), (method, path, r.status)

    asyncio.run(_client_call(monkeypatch, tmp_path, body))


def test_dast_injection_payloads_do_not_authorize(monkeypatch, tmp_path):
    payloads = [
        "' OR '1'='1",
        "../../etc/passwd",
        "<script>alert(1)</script>",
        "%00",
        "{{7*7}}",
        "${jndi:ldap://x}",
    ]

    async def body(client, tid_a, key_a, tid_b, key_b):
        for p in payloads:
            r = await client.get(
                f"/v1/admin/credits/{p}/overview",
                headers={"Authorization": f"Bearer {key_a}"},
            )
            assert r.status in (400, 401, 403, 404)
            r2 = await client.get(
                f"/v1/jobs/{p}",
                headers={"Authorization": f"Bearer {key_a}"},
            )
            assert r2.status in (400, 401, 403, 404)

    asyncio.run(_client_call(monkeypatch, tmp_path, body))


def test_dast_oversized_json_rejected(monkeypatch, tmp_path):
    async def body(client, tid_a, key_a, tid_b, key_b):
        huge = {"description": "A" * 200_000}
        r = await client.post(
            "/v1/generate",
            data=json.dumps(huge),
            headers={
                "Authorization": f"Bearer {key_a}",
                "Content-Type": "application/json",
            },
        )
        assert r.status in (400, 413, 402, 429, 503)

    asyncio.run(_client_call(monkeypatch, tmp_path, body))


def test_dast_dev_activate_not_free_privilege(monkeypatch, tmp_path):
    async def body(client, tid_a, key_a, tid_b, key_b):
        # Without ALLOW_DEV_BILLING must not escalate
        r = await client.post(
            "/v1/billing/dev/activate",
            json={"plan_id": "enterprise"},
            headers={"Authorization": f"Bearer {key_a}"},
        )
        assert r.status in (401, 403)

    asyncio.run(_client_call(monkeypatch, tmp_path, body))
