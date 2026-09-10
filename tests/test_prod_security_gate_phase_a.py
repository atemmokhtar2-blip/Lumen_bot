"""Phase A production hard gates — fail-closed."""
from __future__ import annotations

import pytest


def test_gate_skips_dev(monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "dev")
    from lumen.platform.prod_security_gate import assert_production_security

    assert_production_security()  # must not raise


def test_gate_requires_strong_secrets(monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.delenv("TBE_TOKEN_SECRET", raising=False)
    monkeypatch.delenv("PLATFORM_ADMIN_TOKEN", raising=False)
    monkeypatch.delenv("API_KEY_PEPPER", raising=False)
    monkeypatch.setenv("LUMEN_API_ONLY", "1")
    monkeypatch.setenv("REDIS_URL", "rediss://default:x@host:6380")
    from lumen.platform.prod_security_gate import assert_production_security

    with pytest.raises(RuntimeError, match="production security gate failed"):
        assert_production_security()


def test_gate_rejects_weak_path_flag(monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("TBE_TOKEN_SECRET", "a1b2c3d4e5f6g7h8i9j0k1l2m3n4o5p6")
    monkeypatch.setenv("PLATFORM_ADMIN_TOKEN", "A1B2C3D4E5F6G7H8I9J0K1L2M3N4O5P6")
    monkeypatch.setenv("API_KEY_PEPPER", "p1q2r3s4t5u6v7w8x9y0z1a2b3c4d5e6")
    monkeypatch.setenv("LUMEN_API_ONLY", "1")
    monkeypatch.setenv("REDIS_URL", "rediss://default:x@host:6380")
    monkeypatch.setenv("TBE_ALLOW_WEAK_PATH_OPEN", "1")
    monkeypatch.delenv("TBE_WEAK_PATH_OPEN_ACK", raising=False)
    from lumen.platform.prod_security_gate import assert_production_security

    with pytest.raises(RuntimeError, match="TBE_ALLOW_WEAK_PATH_OPEN"):
        assert_production_security()


def test_gate_rejects_redis_without_tls(monkeypatch):
    from lumen.platform.prod_security_gate import assert_redis_url_tls

    monkeypatch.delenv("REDIS_ALLOW_INSECURE", raising=False)
    with pytest.raises(RuntimeError, match="rediss"):
        assert_redis_url_tls("redis://default:x@host:6379")


def test_gate_accepts_rediss(monkeypatch):
    from lumen.platform.prod_security_gate import assert_redis_url_tls

    assert_redis_url_tls("rediss://default:x@host:6380")


def test_gate_rejects_local_process_flags(monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("TBE_TOKEN_SECRET", "a1b2c3d4e5f6g7h8i9j0k1l2m3n4o5p6")
    monkeypatch.setenv("PLATFORM_ADMIN_TOKEN", "A1B2C3D4E5F6G7H8I9J0K1L2M3N4O5P6")
    monkeypatch.setenv("API_KEY_PEPPER", "p1q2r3s4t5u6v7w8x9y0z1a2b3c4d5e6")
    monkeypatch.setenv("LUMEN_API_ONLY", "1")
    monkeypatch.setenv("REDIS_URL", "rediss://default:x@host:6380")
    monkeypatch.setenv("TBE_ALLOW_LOCAL_PROCESS", "1")
    from lumen.platform.prod_security_gate import assert_production_security

    with pytest.raises(RuntimeError, match="TBE_ALLOW_LOCAL_PROCESS"):
        assert_production_security()


def test_isolation_never_local_in_prod(monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("TBE_MULTI_TENANT", "1")
    monkeypatch.setenv("TBE_ALLOW_LOCAL_PROCESS", "1")
    monkeypatch.setenv("TBE_FORCE_LOCAL_PROCESS", "1")
    from lumen.engine.services.isolation_policy import decide_isolation

    d = decide_isolation()
    assert d.allow_local is False
    assert d.require_strong_isolation is True
