"""Phase C — Argon2/scrypt API keys, SSE single-use shape, HITL grant binding."""
from __future__ import annotations

import os

import pytest


@pytest.fixture(autouse=True)
def _pepper(monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "dev")
    monkeypatch.setenv("API_KEY_PEPPER", "a1b2c3d4e5f6g7h8i9j0k1l2m3n4o5p6")
    monkeypatch.setenv("TBE_TOKEN_SECRET", "a1b2c3d4e5f6g7h8i9j0k1l2m3n4o5p6")


def test_kdf_roundtrip():
    from lumen.platform.api_key_crypto import kdf_hash, kdf_verify

    key = "sk_live_test_" + "x" * 20
    h = kdf_hash(key)
    assert kdf_verify(key, h)
    assert not kdf_verify(key + "nope", h)


def test_legacy_hmac_upgrades():
    from lumen.platform.api_key_crypto import lookup_hmac, verify_stored

    key = "sk_live_legacy_" + "y" * 20
    stored = lookup_hmac(key)
    ok, upgrade = verify_stored(key, stored_hash=stored, stored_kdf="")
    assert ok
    assert upgrade
    assert upgrade.startswith("$argon2") or upgrade.startswith("scrypt$")
    ok2, up2 = verify_stored(key, stored_hash=stored, stored_kdf=upgrade)
    assert ok2 and up2 is None


def test_hash_api_key_is_hmac_index():
    from lumen.platform.api_key_crypto import hash_api_key, lookup_hmac

    key = "sk_live_idx_" + "z" * 20
    assert hash_api_key(key) == lookup_hmac(key)
    assert len(hash_api_key(key)) == 64


def test_sse_ticket_source_has_jti_single_use():
    src = open("lumen/api/auth.py", encoding="utf-8").read()
    assert "jti" in src and "_sse_consume_jti" in src
    assert "tenant_id:job_id:exp:jti" in src or "{tid}:{jid}:{exp}:{jti}" in src
    assert "single-use" in src.lower() or "single_use" in src or "Consume jti" in src


def test_hitl_grant_binds_user_and_digest():
    from lumen.engine.services.multi_agent.hitl import (
        consume_execute_grant,
        _params_digest,
    )
    from types import SimpleNamespace

    params = {"path": "/tmp/x", "msg": "hi"}
    digest = _params_digest(params)
    state = SimpleNamespace(
        user_id=42,
        extensions={
            "hitl_execute_grant": {
                "action_id": "abc",
                "tool": "git_push",
                "user_id": 42,
                "params_digest": digest,
                "single_use": True,
                "granted_at": 1.0,
            },
            "pending_action": None,
        },
        record=lambda *a, **k: None,
    )
    assert consume_execute_grant(state, "git_push", user_id=42, params=params) is True
    # second consume fails
    assert consume_execute_grant(state, "git_push", user_id=42, params=params) is False


def test_hitl_grant_rejects_user_mismatch():
    from lumen.engine.services.multi_agent.hitl import consume_execute_grant
    from types import SimpleNamespace

    state = SimpleNamespace(
        user_id=1,
        extensions={
            "hitl_execute_grant": {
                "tool": "git_push",
                "user_id": 99,
                "params_digest": "",
                "single_use": True,
            }
        },
        record=lambda *a, **k: None,
    )
    assert consume_execute_grant(state, "git_push", user_id=1) is False
