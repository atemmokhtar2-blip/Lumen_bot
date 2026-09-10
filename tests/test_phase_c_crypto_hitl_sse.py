"""Phase C — real wiring: KDF, HITL grant binding, sources."""
from __future__ import annotations

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


def test_legacy_upgrades_to_kdf():
    from lumen.platform.api_key_crypto import lookup_hmac, verify_stored
    key = "sk_live_legacy_" + "y" * 20
    ok, upgrade = verify_stored(key, stored_hash=lookup_hmac(key), stored_kdf="")
    assert ok and upgrade
    ok2, up2 = verify_stored(key, stored_hash=lookup_hmac(key), stored_kdf=upgrade)
    assert ok2 and up2 is None


def test_pg_store_authenticate_source_has_kdf():
    src = open("lumen/platform/pg_store.py", encoding="utf-8").read()
    assert "api_key_kdf" in src
    assert "verify_stored" in src
    assert "lookup_hmac" in src


def test_mongo_authenticate_source_has_kdf():
    src = open("lumen/platform/mongo_users.py", encoding="utf-8").read()
    assert "api_key_kdf" in src
    assert "verify_stored" in src


def test_tools_passes_user_and_params_to_grant():
    src = open("lumen/engine/services/multi_agent/tools.py", encoding="utf-8").read()
    assert "user_id=int(state.user_id" in src
    assert "params=dict(params" in src


def test_hitl_grant_requires_params_when_digest_set():
    from lumen.engine.services.multi_agent.hitl import consume_execute_grant, _params_digest
    from types import SimpleNamespace
    params = {"path": "/tmp/x"}
    digest = _params_digest(params)
    state = SimpleNamespace(
        user_id=42,
        extensions={
            "hitl_execute_grant": {
                "tool": "git_push",
                "user_id": 42,
                "params_digest": digest,
                "single_use": True,
            }
        },
        record=lambda *a, **k: None,
    )
    assert consume_execute_grant(state, "git_push", user_id=42, params=None) is False
    # restore grant for second try
    state.extensions["hitl_execute_grant"] = {
        "tool": "git_push",
        "user_id": 42,
        "params_digest": digest,
        "single_use": True,
    }
    assert consume_execute_grant(state, "git_push", user_id=42, params=params) is True


def test_sse_and_oauth_prod_no_local_fallback():
    auth = open("lumen/api/auth.py", encoding="utf-8").read()
    assert "_sse_consume_jti" in auth and "jti" in auth
    oauth = open("lumen/engine/services/integrations/github/app_oauth_state.py", encoding="utf-8").read()
    assert "oauth_state_nonce_requires_redis" in oauth
