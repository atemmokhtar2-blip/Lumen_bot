"""World-class IDOR + DAST suite — full route matrix, cross-tenant, races, fuzz.

Design goals:
1. Every tenant-scoped route is probed with the *other* tenant's key where applicable.
2. Job/host/credits/billing isolation is proven with planted resources.
3. Privilege escalation (plan_id, admin header spoof, webhook forgery) fails closed.
4. Concurrent credit ops cannot double-spend below zero.
5. Unexpected 2xx on sensitive unauthenticated routes is a hard fail.
"""
from __future__ import annotations

import asyncio
import concurrent.futures
import json
import time
from pathlib import Path
from typing import Any, Awaitable, Callable

import pytest

ADMIN = "world-class-idor-admin-token-32ch"

# Complete tenant-authenticated surface from api/app.py
TENANT_GET = [
    "/v1/me",
    "/v1/me/credits/overview",
    "/v1/me/credits/ledger",
    "/v1/me/credits/reconcile",
    "/v1/jobs",
    "/v1/hosts",
    "/v1/usage",
    "/v1/billing/balance",
    "/v1/invoices",
    "/v1/dashboard",
]
TENANT_POST = [
    "/v1/me/rotate_key",
    "/v1/generate",
    "/v1/hosts/start",
    "/v1/hosts/stop",
    "/v1/hosts/diagnose",
    "/v1/billing/checkout",
    "/v1/billing/credits/checkout",
    "/v1/billing/portal",
    "/v1/billing/dev/activate",
    "/v1/invoices",
]
ADMIN_GET_TMPL = [
    "/v1/admin/credits/{tid}/overview",
    "/v1/admin/credits/{tid}/ledger",
    "/v1/admin/credits/{tid}/reconcile",
]


def _reset(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ENVIRONMENT", "test")
    monkeypatch.setenv("TBE_ENV", "test")
    monkeypatch.setenv("OUTPUT_DIR", str(tmp_path / "out"))
    monkeypatch.setenv("PLATFORM_ADMIN_TOKEN", ADMIN)
    monkeypatch.setenv("TBE_MULTI_TENANT", "0")
    monkeypatch.setenv("TBE_REQUIRE_DOCKER", "0")
    monkeypatch.setenv("TBE_ALLOW_LOCAL_PROCESS", "1")
    monkeypatch.setenv("STRIPE_WEBHOOK_SECRET", "whsec_world_class_idor_dast")
    monkeypatch.setenv("ALLOW_DEV_BILLING", "0")
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("POSTGRES_URL", raising=False)

    import lumen.platform.tenants as tenants_mod
    import lumen.platform.credits.service as credits_mod
    import lumen.platform.billing as billing_mod
    import lumen.platform.jobs as jobs_mod

    tenants_mod._STORE = None
    credits_mod._SVC = None
    try:
        credits_mod.reset_credit_service_for_tests()
    except Exception:
        pass
    try:
        billing_mod._BILL = None
    except Exception:
        pass
    # jobs runner may cache paths under OUTPUT_DIR — new OUTPUT_DIR is enough


async def _world(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    fn: Callable[[Any, dict], Awaitable[None]],
) -> None:
    _reset(tmp_path, monkeypatch)
    from aiohttp.test_utils import TestClient, TestServer
    from lumen.api.app import create_app
    from lumen.platform.tenants import get_tenant_store
    from lumen.platform.credits import get_credit_service

    store = get_tenant_store()
    ten_a, key_a = store.create("WorldA")
    ten_b, key_b = store.create("WorldB")
    svc = get_credit_service()
    # Distinct paid balances for isolation asserts
    svc.credit_credits(ten_a.tenant_id, 900, reason="purchase", idempotency_key="wc-fund-a-0001")
    svc.credit_credits(ten_b.tenant_id, 50, reason="purchase", idempotency_key="wc-fund-b-0001")

    # Plant a job owned by A (IDOR bait)
    import uuid
    from lumen.platform.jobs import Job, get_job_runner
    import lumen.platform.jobs as jobs_mod
    jobs_mod._RUNNER = None
    jobs_mod._HANDLERS_READY = False
    runner = get_job_runner()
    planted = Job(
        job_id=f"job_{uuid.uuid4().hex[:16]}",
        tenant_id=ten_a.tenant_id,
        kind="generate",
        input={"description": "secret-of-A"},
        message="planted",
    )
    runner.store.create(planted)

    ctx = {
        "tid_a": ten_a.tenant_id,
        "key_a": key_a,
        "tid_b": ten_b.tenant_id,
        "key_b": key_b,
        "job_a": planted.job_id,
        "svc": svc,
        "store": store,
    }
    app = create_app()
    async with TestClient(TestServer(app)) as client:
        await fn(client, ctx)


# ── Matrix: unauthenticated sensitive routes never 2xx ─────────────────────

def test_matrix_unauthenticated_sensitive_never_2xx(monkeypatch, tmp_path):
    async def body(client, ctx):
        for path in TENANT_GET + TENANT_POST:
            for method in ("GET", "POST", "PUT", "PATCH", "DELETE"):
                r = await client.request(method, path)
                assert not (200 <= r.status < 300), (method, path, r.status)
        for tmpl in ADMIN_GET_TMPL:
            path = tmpl.format(tid=ctx["tid_a"])
            r = await client.get(path)
            assert r.status in (401, 403)

    asyncio.run(_world(monkeypatch, tmp_path, body))


# ── Matrix: tenant key cannot hit admin for other (or self) without admin ──

def test_matrix_tenant_key_never_admin(monkeypatch, tmp_path):
    async def body(client, ctx):
        for key in (ctx["key_a"], ctx["key_b"]):
            for tid in (ctx["tid_a"], ctx["tid_b"]):
                for tmpl in ADMIN_GET_TMPL:
                    r = await client.get(
                        tmpl.format(tid=tid),
                        headers={"Authorization": f"Bearer {key}", "X-Admin-Token": key},
                    )
                    assert r.status in (401, 403), (key[:8], tid, tmpl, r.status)

    asyncio.run(_world(monkeypatch, tmp_path, body))


# ── /v1/me isolation ───────────────────────────────────────────────────────

def test_idor_me_identity_strict(monkeypatch, tmp_path):
    async def body(client, ctx):
        ra = await client.get("/v1/me", headers={"Authorization": f"Bearer {ctx['key_a']}"})
        rb = await client.get("/v1/me", headers={"Authorization": f"Bearer {ctx['key_b']}"})
        assert ra.status == 200 and rb.status == 200
        ja, jb = await ra.json(), await rb.json()
        assert ja["tenant"]["tenant_id"] == ctx["tid_a"]
        assert jb["tenant"]["tenant_id"] == ctx["tid_b"]
        # Must not leak the other tenant id anywhere in payload
        assert ctx["tid_b"] not in json.dumps(ja)
        assert ctx["tid_a"] not in json.dumps(jb)

    asyncio.run(_world(monkeypatch, tmp_path, body))


# ── Credits isolation across all me/credits routes ─────────────────────────

def test_idor_credits_all_routes_isolated(monkeypatch, tmp_path):
    async def body(client, ctx):
        bals = {}
        for label, key in (("a", ctx["key_a"]), ("b", ctx["key_b"])):
            for path in (
                "/v1/me/credits/overview",
                "/v1/me/credits/ledger",
                "/v1/me/credits/reconcile",
                "/v1/billing/balance",
            ):
                r = await client.get(path, headers={"Authorization": f"Bearer {key}"})
                assert r.status == 200, (path, r.status, await r.text())
                data = await r.json()
                blob = json.dumps(data)
                other = ctx["tid_b"] if label == "a" else ctx["tid_a"]
                assert other not in blob
            # overview/balance balance markers
            r = await client.get(
                "/v1/me/credits/overview",
                headers={"Authorization": f"Bearer {key}"},
            )
            data = await r.json()
            bals[label] = int(
                (data.get("wallet") or {}).get("current_balance")
                or data.get("current_balance")
                or 0
            )
        assert bals["a"] != bals["b"]
        assert bals["a"] >= 900

    asyncio.run(_world(monkeypatch, tmp_path, body))


# ── Job IDOR ───────────────────────────────────────────────────────────────

def test_idor_job_owned_by_a_invisible_to_b(monkeypatch, tmp_path):
    async def body(client, ctx):
        job_id = ctx["job_a"]
        ra = await client.get(
            f"/v1/jobs/{job_id}",
            headers={"Authorization": f"Bearer {ctx['key_a']}"},
        )
        rb = await client.get(
            f"/v1/jobs/{job_id}",
            headers={"Authorization": f"Bearer {ctx['key_b']}"},
        )
        # A may see 200; B must not see A's job content
        assert rb.status in (403, 404)
        if ra.status == 200:
            body_a = await ra.json()
            assert body_a.get("job", body_a).get("tenant_id", ctx["tid_a"]) in (
                ctx["tid_a"],
                None,
            ) or ctx["tid_a"] in json.dumps(body_a)

        # list_jobs for B must not include A's job_id
        rl = await client.get("/v1/jobs", headers={"Authorization": f"Bearer {ctx['key_b']}"})
        assert rl.status == 200
        listed = json.dumps(await rl.json())
        assert job_id not in listed

    asyncio.run(_world(monkeypatch, tmp_path, body))


# ── Usage / invoices / dashboard isolation ────────────────────────────────

def test_idor_usage_invoices_dashboard_no_cross_leak(monkeypatch, tmp_path):
    async def body(client, ctx):
        for path in ("/v1/usage", "/v1/invoices", "/v1/dashboard"):
            ra = await client.get(path, headers={"Authorization": f"Bearer {ctx['key_a']}"})
            rb = await client.get(path, headers={"Authorization": f"Bearer {ctx['key_b']}"})
            assert ra.status == 200 and rb.status == 200
            assert ctx["tid_b"] not in json.dumps(await ra.json())
            assert ctx["tid_a"] not in json.dumps(await rb.json())

    asyncio.run(_world(monkeypatch, tmp_path, body))


# ── Mass assignment / privilege escalation ────────────────────────────────

def test_escalation_white_label_cannot_set_plan(monkeypatch, tmp_path):
    async def body(client, ctx):
        r = await client.patch(
            "/v1/me/white-label",
            json={
                "brand_name": "Hack",
                "plan_id": "enterprise",
                "active": True,
                "api_key": "stolen",
            },
            headers={"Authorization": f"Bearer {ctx['key_a']}"},
        )
        # Either forbidden (no white_label plan) or applied only to allow-listed fields
        if r.status == 200:
            me = await client.get("/v1/me", headers={"Authorization": f"Bearer {ctx['key_a']}"})
            data = await me.json()
            assert data["tenant"]["plan_id"] != "enterprise"
            assert data["tenant"].get("api_key") is None

    asyncio.run(_world(monkeypatch, tmp_path, body))


def test_escalation_create_tenant_requires_admin(monkeypatch, tmp_path):
    async def body(client, ctx):
        r = await client.post(
            "/v1/tenants",
            json={"name": "Evil", "plan_id": "enterprise"},
            headers={"Authorization": f"Bearer {ctx['key_a']}"},
        )
        assert r.status in (401, 403)
        r2 = await client.post(
            "/v1/tenants",
            json={"name": "Evil2", "plan_id": "enterprise"},
        )
        assert r2.status in (401, 403)

    asyncio.run(_world(monkeypatch, tmp_path, body))


def test_escalation_dev_activate_locked(monkeypatch, tmp_path):
    async def body(client, ctx):
        r = await client.post(
            "/v1/billing/dev/activate",
            json={"plan_id": "enterprise"},
            headers={"Authorization": f"Bearer {ctx['key_a']}"},
        )
        assert r.status in (401, 403)

    asyncio.run(_world(monkeypatch, tmp_path, body))


# ── Auth confusion ────────────────────────────────────────────────────────

def test_auth_header_confusion(monkeypatch, tmp_path):
    async def body(client, ctx):
        # Empty bearer
        r = await client.get("/v1/me", headers={"Authorization": "Bearer "})
        assert r.status == 401
        # Admin token as bearer must not authenticate as tenant
        r2 = await client.get("/v1/me", headers={"Authorization": f"Bearer {ADMIN}"})
        assert r2.status == 401
        # X-Api-Key valid
        r3 = await client.get("/v1/me", headers={"X-Api-Key": ctx["key_a"]})
        assert r3.status == 200
        # Wrong key
        r4 = await client.get("/v1/me", headers={"X-Api-Key": "sk_live_not_real_key_xxxxx"})
        assert r4.status == 401

    asyncio.run(_world(monkeypatch, tmp_path, body))


# ── Stripe webhook forgery + replay shape ─────────────────────────────────

def test_dast_stripe_webhook_forged_and_empty(monkeypatch, tmp_path):
    async def body(client, ctx):
        payloads = [
            b"{}",
            b'{"type":"checkout.session.completed","data":{"object":{"metadata":{"credits_amount":"999999","product_type":"credits","tenant_id":"'
            + ctx["tid_a"].encode()
            + b'"}}}}',
        ]
        for raw in payloads:
            r = await client.post(
                "/v1/billing/webhook/stripe",
                data=raw,
                headers={"Content-Type": "application/json"},
            )
            assert r.status in (400, 401, 403)
            r2 = await client.post(
                "/v1/billing/webhook/stripe",
                data=raw,
                headers={
                    "Content-Type": "application/json",
                    "Stripe-Signature": "t=1,v1=000000",
                },
            )
            assert r2.status in (400, 401, 403)
        # Balance of A must not jump by forged 999999
        from lumen.platform.credits import get_credit_service

        w = get_credit_service().get_wallet(ctx["tid_a"])
        assert w.current_balance < 50_000

    asyncio.run(_world(monkeypatch, tmp_path, body))


# ── Injection / path abuse ────────────────────────────────────────────────

def test_dast_injection_matrix(monkeypatch, tmp_path):
    payloads = [
        "../" * 8 + "etc/passwd",
        "1 OR 1=1",
        "' OR '1'='1",
        "<script>alert(1)</script>",
        "%00admin",
        "{{7*7}}",
        "${jndi:ldap://127.0.0.1/a}",
        "..%2f..%2fetc%2fpasswd",
        "ten_" + "a" * 500,
    ]

    async def body(client, ctx):
        for p in payloads:
            for tmpl in ADMIN_GET_TMPL:
                r = await client.get(
                    tmpl.format(tid=p),
                    headers={"Authorization": f"Bearer {ctx['key_a']}"},
                )
                assert r.status in (400, 401, 403, 404)
            r2 = await client.get(
                f"/v1/jobs/{p}",
                headers={"Authorization": f"Bearer {ctx['key_a']}"},
            )
            assert r2.status in (400, 401, 403, 404)

    asyncio.run(_world(monkeypatch, tmp_path, body))


# ── Oversized body ────────────────────────────────────────────────────────

def test_dast_oversized_generate_is_413_not_500(monkeypatch, tmp_path):
    async def body(client, ctx):
        huge = json.dumps({"description": "X" * 200_000})
        r = await client.post(
            "/v1/generate",
            data=huge,
            headers={
                "Authorization": f"Bearer {ctx['key_a']}",
                "Content-Type": "application/json",
            },
        )
        assert r.status == 413
        assert r.status != 500

    asyncio.run(_world(monkeypatch, tmp_path, body))


# ── Concurrent credit deduct race (no negative wallet) ────────────────────

def test_race_parallel_deduct_cannot_go_negative():
    from lumen.platform.credits.memory_store import MemoryCreditsStore
    from lumen.platform.credits.service import CreditService

    svc = CreditService(MemoryCreditsStore())
    tid = "race_tenant"
    assert svc.credit_credits(tid, 100, reason="purchase", idempotency_key="race-fund-0001").ok

    def once(i: int):
        return svc.deduct_credits(
            tid, 60, idempotency_key=f"race-deduct-{i:04d}"
        ).ok

    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(once, range(8)))
    successes = sum(1 for x in results if x)
    # Only one 60-debit can succeed from 100 (second needs another 60)
    assert successes <= 1
    w = svc.get_wallet(tid)
    assert w.current_balance >= 0
    assert w.current_balance == 100 - 60 * successes
    assert svc.reconcile(tid).ok


# ── Rotate key isolation ──────────────────────────────────────────────────

def test_idor_rotate_key_does_not_break_other_tenant(monkeypatch, tmp_path):
    async def body(client, ctx):
        r = await client.post(
            "/v1/me/rotate_key",
            headers={"Authorization": f"Bearer {ctx['key_a']}"},
        )
        assert r.status == 200
        new_a = (await r.json()).get("api_key")
        assert new_a and new_a != ctx["key_a"]
        # Old A key dead
        old = await client.get("/v1/me", headers={"Authorization": f"Bearer {ctx['key_a']}"})
        assert old.status == 401
        # New A works
        ok = await client.get("/v1/me", headers={"Authorization": f"Bearer {new_a}"})
        assert ok.status == 200
        # B unaffected
        b = await client.get("/v1/me", headers={"Authorization": f"Bearer {ctx['key_b']}"})
        assert b.status == 200
        assert (await b.json())["tenant"]["tenant_id"] == ctx["tid_b"]

    asyncio.run(_world(monkeypatch, tmp_path, body))


# ── Admin positive control ────────────────────────────────────────────────

def test_admin_token_reads_both_tenants(monkeypatch, tmp_path):
    async def body(client, ctx):
        for tid in (ctx["tid_a"], ctx["tid_b"]):
            for tmpl in ADMIN_GET_TMPL:
                r = await client.get(
                    tmpl.format(tid=tid),
                    headers={"X-Admin-Token": ADMIN},
                )
                assert r.status == 200, (tmpl, tid, r.status, await r.text())

    asyncio.run(_world(monkeypatch, tmp_path, body))


# ── Layer-2 closure: identity spoof + ownership helpers ─────────────────────

def test_spoof_tenant_id_in_generate_body_rejected(monkeypatch, tmp_path):
    async def body(client, ctx):
        r = await client.post(
            "/v1/generate",
            json={
                "description": "بوت تجريبي لاختبار العزل",
                "tenant_id": ctx["tid_b"],
            },
            headers={"Authorization": f"Bearer {ctx['key_a']}"},
        )
        assert r.status == 403
        data = await r.json()
        assert data.get("error") == "tenant_spoof_rejected"

    asyncio.run(_world(monkeypatch, tmp_path, body))


def test_spoof_tenant_id_in_host_start_rejected(monkeypatch, tmp_path):
    async def body(client, ctx):
        r = await client.post(
            "/v1/hosts/start",
            json={
                "project_path": "proj",
                "bot_token": "123:ABC",
                "tenant_id": ctx["tid_b"],
                "user_id": 999999,
            },
            headers={"Authorization": f"Bearer {ctx['key_a']}"},
        )
        assert r.status == 403

    asyncio.run(_world(monkeypatch, tmp_path, body))


def test_spoof_tenant_id_in_credits_checkout_rejected(monkeypatch, tmp_path):
    async def body(client, ctx):
        r = await client.post(
            "/v1/billing/credits/checkout",
            json={"credits_amount": 100, "tenant_id": ctx["tid_b"]},
            headers={"Authorization": f"Bearer {ctx['key_a']}"},
        )
        assert r.status == 403

    asyncio.run(_world(monkeypatch, tmp_path, body))


def test_admin_invalid_tenant_id_rejected(monkeypatch, tmp_path):
    async def body(client, ctx):
        for bad in ("../etc/passwd", "a/b", "x" * 200, "ten_../../x"):
            r = await client.get(
                f"/v1/admin/credits/{bad}/overview",
                headers={"X-Admin-Token": ADMIN},
            )
            assert r.status in (400, 404)

    asyncio.run(_world(monkeypatch, tmp_path, body))


def test_job_response_strips_input_payload(monkeypatch, tmp_path):
    async def body(client, ctx):
        r = await client.get(
            f"/v1/jobs/{ctx['job_a']}",
            headers={"Authorization": f"Bearer {ctx['key_a']}"},
        )
        assert r.status == 200
        data = await r.json()
        assert data.get("input") in ({}, None)
        assert "secret-of-A" not in json.dumps(data)

    asyncio.run(_world(monkeypatch, tmp_path, body))


def test_ownership_module_normalize():
    from aiohttp import web
    from lumen.api.ownership import normalize_tenant_id, reject_identity_spoof
    import pytest as _pt

    assert normalize_tenant_id("ten_abc123") == "ten_abc123"
    with _pt.raises(web.HTTPBadRequest):
        normalize_tenant_id("../x")
    with _pt.raises(web.HTTPForbidden):
        reject_identity_spoof({"tenant_id": "other"}, tenant_id="ten_self")
    reject_identity_spoof({"tenant_id": "ten_self"}, tenant_id="ten_self")
    reject_identity_spoof({}, tenant_id="ten_self")
