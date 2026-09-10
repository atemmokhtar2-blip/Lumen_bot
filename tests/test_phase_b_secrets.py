"""Phase B — secrets managed keys, PAT gate, rotation helpers."""
from __future__ import annotations

import pytest


def test_managed_keys_include_github_app():
    from lumen.platform.secrets_provider import _MANAGED_KEYS

    assert "GITHUB_APP_PRIVATE_KEY" in _MANAGED_KEYS
    assert "STRIPE_WEBHOOK_SECRET" in _MANAGED_KEYS
    assert "CALLBACK_HMAC_SECRET" in _MANAGED_KEYS


def test_platform_env_fallback_requires_ack(monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "production")
    for m in ("RAILWAY_ENVIRONMENT", "RENDER_SERVICE_ID", "FLY_APP_NAME", "K_SERVICE", "DYNO", "AWS_EXECUTION_ENV", "AWS_REGION", "KUBERNETES_SERVICE_HOST"):
        monkeypatch.delenv(m, raising=False)
    monkeypatch.delenv("SECRETS_REQUIRE_MANAGED_PROVIDER", raising=False)
    monkeypatch.delenv("SECRETS_ALLOW_PLATFORM_ENV", raising=False)
    monkeypatch.delenv("SECRETS_PLATFORM_ENV_ACK", raising=False)
    # Force non-dev via ENVIRONMENT only — tenants helper may still see markers
    from lumen.platform import secrets_provider as sp

    # If deploy markers absent and env production, platform fallback should be False
    # without ACK — patch _is_dev_environment
    monkeypatch.setattr(sp, "_is_dev_environment", lambda: False)
    assert sp._allow_platform_env_fallback() is False
    monkeypatch.setenv("SECRETS_PLATFORM_ENV_ACK", "I_ACCEPT_PLATFORM_ENV_SECRETS")
    assert sp._allow_platform_env_fallback() is True


def test_pat_allowed_requires_dual_ack(monkeypatch):
    from lumen.platform.secret_rotation import pat_allowed_in_production

    monkeypatch.delenv("GITHUB_ALLOW_PAT", raising=False)
    monkeypatch.delenv("GITHUB_ALLOW_PAT_ACK", raising=False)
    assert pat_allowed_in_production() is False
    monkeypatch.setenv("GITHUB_ALLOW_PAT", "1")
    assert pat_allowed_in_production() is False
    monkeypatch.setenv("GITHUB_ALLOW_PAT_ACK", "I_ACCEPT_USER_PAT_IN_PROD")
    assert pat_allowed_in_production() is True


def test_resolve_pat_refused_in_prod(monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "production")
    for m in ("RAILWAY_ENVIRONMENT", "RENDER_SERVICE_ID", "FLY_APP_NAME", "K_SERVICE", "DYNO", "AWS_EXECUTION_ENV"):
        monkeypatch.delenv(m, raising=False)
    monkeypatch.delenv("GITHUB_ALLOW_PAT", raising=False)
    from lumen.engine.services.integrations.connections import credentials as cred

    monkeypatch.setattr(cred, "_profile_for", lambda uid: {"connected": True, "auth_kind": "pat", "login": "u"})
    monkeypatch.setattr(
        "lumen.engine.services.integrations.connections.token_store.load_github_token",
        lambda uid: "ghp_TEST_ONLY_NOT_REAL_xxxxxxxxxxxx",
        raising=False,
    )
    # force production path
    monkeypatch.setattr(
        "lumen.platform.prod_security_gate.is_production_runtime",
        lambda: True,
    )
    monkeypatch.setattr(
        "lumen.platform.secret_rotation.pat_allowed_in_production",
        lambda: False,
    )
    # Also patch local _pat_path_allowed
    monkeypatch.setattr(cred, "_pat_path_allowed", lambda: False)
    result = cred.resolve_github_credentials(42)
    # May still try app path first with empty install — should be None
    assert result is None or result.auth_kind != "pat"


def test_gate_rejects_pat_flag_without_ack(monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "production")
    for m in ("RAILWAY_ENVIRONMENT", "RENDER_SERVICE_ID", "FLY_APP_NAME", "K_SERVICE", "DYNO", "AWS_EXECUTION_ENV"):
        monkeypatch.delenv(m, raising=False)
    monkeypatch.setenv("TBE_TOKEN_SECRET", "a1b2c3d4e5f6g7h8i9j0k1l2m3n4o5p6")
    monkeypatch.setenv("PLATFORM_ADMIN_TOKEN", "A1B2C3D4E5F6G7H8I9J0K1L2M3N4O5P6")
    monkeypatch.setenv("API_KEY_PEPPER", "p1q2r3s4t5u6v7w8x9y0z1a2b3c4d5e6")
    monkeypatch.setenv("LUMEN_API_ONLY", "1")
    monkeypatch.setenv("REDIS_URL", "rediss://default:x@host:6380")
    monkeypatch.setenv("GITHUB_ALLOW_PAT", "1")
    monkeypatch.delenv("GITHUB_ALLOW_PAT_ACK", raising=False)
    # Avoid rotation redis noise
    monkeypatch.setenv("SECRET_ROTATION_FAIL_CLOSED", "0")
    from lumen.platform.prod_security_gate import assert_production_security

    with pytest.raises(RuntimeError, match="GITHUB_ALLOW_PAT"):
        assert_production_security()


def test_write_github_connection_refuses_prod_pat(monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "dev")
    monkeypatch.setenv("SECRETS_ALLOW_PLATFORM_ENV", "1")
    monkeypatch.setattr(
        "lumen.platform.prod_security_gate.is_production_runtime",
        lambda: True,
    )
    monkeypatch.setattr(
        "lumen.platform.secret_rotation.pat_allowed_in_production",
        lambda: False,
    )
    import lumen.bot.ui.github_connection_store as gcs
    monkeypatch.setattr(
        gcs,
        "is_production_runtime",
        lambda: True,
        raising=False,
    )
    # Patch at module used inside function
    import lumen.platform.prod_security_gate as psg
    monkeypatch.setattr(psg, "is_production_runtime", lambda: True)
    import lumen.platform.secret_rotation as sr
    monkeypatch.setattr(sr, "pat_allowed_in_production", lambda: False)
    assert gcs.write_github_connection(1, "ghp_TEST_ONLY_NOT_REAL_xxxxxxxxxxxx") is False


def test_admin_uses_get_secret_path():
    src = open("lumen/api/auth.py", encoding="utf-8").read()
    assert 'get_secret("PLATFORM_ADMIN_TOKEN"' in src


def test_stripe_uses_managed_secret():
    src = open("lumen/platform/stripe_client.py", encoding="utf-8").read()
    assert "_managed" in src
    assert "STRIPE_WEBHOOK_SECRET" in src


def test_secret_rotation_routes_registered():
    src = open("lumen/api/app.py", encoding="utf-8").read()
    assert "/v1/admin/secret-rotation" in src


def test_rotation_does_not_silent_baseline(monkeypatch):
    """Without bootstrap ACK, never_recorded stays a problem (not auto-healed)."""
    monkeypatch.setenv("ENVIRONMENT", "production")
    for m in ("RAILWAY_ENVIRONMENT", "RENDER_SERVICE_ID", "FLY_APP_NAME", "K_SERVICE", "DYNO", "AWS_EXECUTION_ENV"):
        monkeypatch.delenv(m, raising=False)
    monkeypatch.delenv("SECRET_ROTATION_BOOTSTRAP_ACK", raising=False)
    monkeypatch.setenv("SECRET_ROTATION_FAIL_CLOSED", "1")
    monkeypatch.setattr(
        "lumen.platform.secret_rotation.last_rotation_ts",
        lambda name: None,
    )
    monkeypatch.setattr(
        "lumen.platform.secret_rotation._redis",
        lambda: None,
    )
    from lumen.platform.secret_rotation import assert_rotation_policy
    with pytest.raises(RuntimeError, match="never_recorded|rotation"):
        assert_rotation_policy(fail_closed=True)


def test_get_secret_no_environ_for_managed_in_prod(monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "production")
    for m in ("RAILWAY_ENVIRONMENT", "RENDER_SERVICE_ID", "FLY_APP_NAME", "K_SERVICE", "DYNO", "AWS_EXECUTION_ENV"):
        monkeypatch.delenv(m, raising=False)
    monkeypatch.setenv("PLATFORM_ADMIN_TOKEN", "should_not_be_read_from_environ_after_scrub")
    from lumen.platform import secrets_provider as sp
    monkeypatch.setattr(sp, "is_production", lambda: True)
    # empty store
    with sp._LOCK:
        sp._STORE.clear()
    assert sp.get_secret("PLATFORM_ADMIN_TOKEN", "") == ""
