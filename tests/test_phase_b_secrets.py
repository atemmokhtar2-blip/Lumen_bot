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
