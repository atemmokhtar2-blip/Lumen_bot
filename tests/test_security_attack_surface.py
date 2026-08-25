"""Offensive security tests — prove controls resist real attack patterns."""
from __future__ import annotations

import asyncio
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def test_attack_infinite_promo_without_expiry_rejected():
    from b2b_platform.credits.memory_store import MemoryCreditsStore
    from b2b_platform.credits.service import CreditService

    svc = CreditService(MemoryCreditsStore())
    r = svc.credit_credits(
        "attacker",
        1_000_000,
        reason="welcome_grant",
        idempotency_key="welcome-grant-attacker-inf",
        promotional=True,
        promo_expires_at=0,
    )
    assert not r.ok
    assert r.reason == "promotional_requires_expiry"


def test_attack_promo_flag_on_purchase_rejected():
    from b2b_platform.credits.memory_store import MemoryCreditsStore
    from b2b_platform.credits.service import CreditService

    svc = CreditService(MemoryCreditsStore())
    r = svc.credit_credits(
        "attacker",
        5000,
        reason="purchase",
        idempotency_key="purchase-as-promo-0001",
        promotional=True,
        promo_expires_at=time.time() + 99999,
    )
    assert not r.ok


def test_attack_double_welcome_does_not_stack():
    from b2b_platform.credits.memory_store import MemoryCreditsStore
    from b2b_platform.credits.onboarding import grant_welcome_credits
    from b2b_platform.credits.service import CreditService

    svc = CreditService(MemoryCreditsStore())
    a = grant_welcome_credits("ten_double", credit_service=svc)
    b = grant_welcome_credits("ten_double", credit_service=svc)
    assert a["ok"] and b["ok"]
    assert svc.get_wallet("ten_double").current_balance == a["amount"]


def test_attack_expired_promo_cannot_fund_hosting_reserve():
    from b2b_platform.credits.memory_store import MemoryCreditsStore
    from b2b_platform.credits.service import CreditService

    svc = CreditService(MemoryCreditsStore())
    assert svc.credit_credits(
        "ten_host",
        500,
        reason="welcome_grant",
        idempotency_key="welcome-grant-ten_host",
        promotional=True,
        promo_expires_at=time.time() - 10,
    ).ok
    assert svc.get_wallet("ten_host").available == 0
    r = svc.reserve_credits("ten_host", 50, idempotency_key="reserve-host-attack-1")
    assert not r.ok


def test_attack_unknown_tool_denied_by_policy():
    from telegram_bot_engine.security.policy import PolicyEngine, ToolRequest

    d = PolicyEngine().evaluate(
        ToolRequest(tool_name="rm_rf_production", params={"path": "/"})
    )
    assert d.allowed is False


def test_attack_git_push_without_confirm_blocked():
    from telegram_bot_engine.security.policy import PolicyEngine, ToolRequest

    d = PolicyEngine().evaluate(ToolRequest(tool_name="git_push", params={"repo": "x"}))
    assert d.needs_confirmation is True
    assert d.allowed is False


def test_attack_path_traversal_rejected():
    from api.security import validate_tenant_project_path

    for payload in ("../../etc/passwd", "/etc/passwd", "proj/../../../etc/shadow"):
        with pytest.raises(ValueError):
            validate_tenant_project_path("ten_x", payload)


def test_attack_admin_token_empty_env_fail_closed(monkeypatch):
    from aiohttp import web
    from aiohttp.test_utils import make_mocked_request
    import api.auth as auth

    monkeypatch.delenv("PLATFORM_ADMIN_TOKEN", raising=False)
    req = make_mocked_request("GET", "/v1/admin/credits/t1/overview")
    with pytest.raises(web.HTTPForbidden):
        auth.require_admin(req)


def test_attack_admin_token_wrong_rejected(monkeypatch):
    from aiohttp import web
    from aiohttp.test_utils import make_mocked_request
    import api.auth as auth

    monkeypatch.setenv("PLATFORM_ADMIN_TOKEN", "correct-admin-secret-value-32chars")
    req = make_mocked_request(
        "GET",
        "/v1/admin/credits/t1/overview",
        headers={"X-Admin-Token": "wrong-token-guess"},
    )
    with pytest.raises(web.HTTPUnauthorized):
        auth.require_admin(req)


def test_attack_admin_token_compare_safe():
    from api.security import admin_token_matches

    assert admin_token_matches("", "secret") is False
    assert admin_token_matches("secret", "") is False
    assert admin_token_matches("secret", "secret") is True
    assert admin_token_matches("secret1", "secret2") is False


def test_security_event_emitted_on_admin_reject(monkeypatch, tmp_path):
    from aiohttp import web
    from aiohttp.test_utils import make_mocked_request
    import api.auth as auth

    monkeypatch.setenv("PLATFORM_ADMIN_TOKEN", "real-admin-secret-token-value")
    monkeypatch.setenv("SECURITY_EVENTS_DIR", str(tmp_path / "sec"))
    monkeypatch.setenv("SECURITY_EVENTS_ENABLED", "1")

    req = make_mocked_request(
        "GET",
        "/v1/admin/credits/x/overview",
        headers={"X-Admin-Token": "bad"},
    )
    with pytest.raises(web.HTTPUnauthorized):
        auth.require_admin(req)

    files = list((tmp_path / "sec").glob("*.jsonl"))
    assert files, "expected security event log file"
    assert "auth.admin_rejected" in files[0].read_text(encoding="utf-8")


async def _with_client(monkeypatch, tmp_path, coro_fn):
    monkeypatch.setenv("PLATFORM_ADMIN_TOKEN", "test-admin-token-for-attack-suite-xx")
    monkeypatch.setenv("OUTPUT_DIR", str(tmp_path / "out"))
    monkeypatch.setenv("TBE_MULTI_TENANT", "0")
    monkeypatch.setenv("TBE_REQUIRE_DOCKER", "0")
    monkeypatch.setenv("TBE_ALLOW_LOCAL_PROCESS", "1")
    monkeypatch.setenv("ENVIRONMENT", "test")
    try:
        from b2b_platform.credits.service import reset_credit_service_for_tests

        reset_credit_service_for_tests()
    except Exception:
        pass

    from aiohttp.test_utils import TestClient, TestServer
    from api.app import create_app

    app = create_app()
    async with TestClient(TestServer(app)) as client:
        return await coro_fn(client)


def test_attack_admin_credits_without_token_401(monkeypatch, tmp_path):
    async def body(client):
        r = await client.get("/v1/admin/credits/ten_any/overview")
        assert r.status in (401, 403)

    asyncio.run(_with_client(monkeypatch, tmp_path, body))


def test_attack_admin_credits_with_wrong_token_401(monkeypatch, tmp_path):
    async def body(client):
        r = await client.get(
            "/v1/admin/credits/ten_any/ledger",
            headers={"X-Admin-Token": "nope"},
        )
        assert r.status in (401, 403)

    asyncio.run(_with_client(monkeypatch, tmp_path, body))


def test_attack_me_credits_without_api_key_401(monkeypatch, tmp_path):
    async def body(client):
        r = await client.get("/v1/me/credits/overview")
        assert r.status == 401

    asyncio.run(_with_client(monkeypatch, tmp_path, body))


def test_attack_generate_without_api_key_401(monkeypatch, tmp_path):
    async def body(client):
        r = await client.post("/v1/generate", json={"description": "بوت تجريبي"})
        assert r.status == 401

    asyncio.run(_with_client(monkeypatch, tmp_path, body))


def test_security_headers_present_on_response(monkeypatch, tmp_path):
    async def body(client):
        r = await client.get("/health")
        assert r.headers.get("X-Content-Type-Options") == "nosniff"
        assert r.headers.get("X-Frame-Options") == "DENY"
        assert "Content-Security-Policy" in r.headers

    asyncio.run(_with_client(monkeypatch, tmp_path, body))
