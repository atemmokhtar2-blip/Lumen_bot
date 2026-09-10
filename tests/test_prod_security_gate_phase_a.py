"""Phase A — complete fail-closed gates with dual-ACK and runtime wiring."""
from __future__ import annotations

from pathlib import Path

import pytest


def test_gate_skips_non_production(monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "dev")
    for m in ("RAILWAY_ENVIRONMENT", "RENDER_SERVICE_ID", "FLY_APP_NAME", "K_SERVICE", "DYNO", "AWS_EXECUTION_ENV"):
        monkeypatch.delenv(m, raising=False)
    from lumen.platform.prod_security_gate import assert_production_security
    assert_production_security()


def _strong_secrets(monkeypatch):
    monkeypatch.setenv("TBE_TOKEN_SECRET", "a1b2c3d4e5f6g7h8i9j0k1l2m3n4o5p6")
    monkeypatch.setenv("PLATFORM_ADMIN_TOKEN", "A1B2C3D4E5F6G7H8I9J0K1L2M3N4O5P6")
    monkeypatch.setenv("API_KEY_PEPPER", "p1q2r3s4t5u6v7w8x9y0z1a2b3c4d5e6")
    monkeypatch.setenv("LUMEN_API_ONLY", "1")
    monkeypatch.setenv("REDIS_URL", "rediss://default:x@host:6380")


def test_gate_requires_dual_ack_for_weak_path(monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "production")
    for m in ("RAILWAY_ENVIRONMENT", "RENDER_SERVICE_ID", "FLY_APP_NAME", "K_SERVICE", "DYNO", "AWS_EXECUTION_ENV"):
        monkeypatch.delenv(m, raising=False)
    _strong_secrets(monkeypatch)
    monkeypatch.setenv("TBE_ALLOW_WEAK_PATH_OPEN", "1")
    monkeypatch.delenv("TBE_WEAK_PATH_OPEN_ACK", raising=False)
    from lumen.platform.prod_security_gate import assert_production_security
    with pytest.raises(RuntimeError, match="TBE_ALLOW_WEAK_PATH_OPEN"):
        assert_production_security()


def test_gate_accepts_weak_path_with_dual_ack(monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "production")
    for m in ("RAILWAY_ENVIRONMENT", "RENDER_SERVICE_ID", "FLY_APP_NAME", "K_SERVICE", "DYNO", "AWS_EXECUTION_ENV"):
        monkeypatch.delenv(m, raising=False)
    _strong_secrets(monkeypatch)
    monkeypatch.setenv("TBE_ALLOW_WEAK_PATH_OPEN", "1")
    monkeypatch.setenv("TBE_WEAK_PATH_OPEN_ACK", "I_ACCEPT_WEAK_PATH_OPEN")
    from lumen.platform.prod_security_gate import assert_production_security
    assert_production_security()


def test_gate_rejects_redis_plain():
    from lumen.platform.prod_security_gate import assert_redis_url_tls
    import os
    os.environ["ENVIRONMENT"] = "production"
    for m in ("RAILWAY_ENVIRONMENT", "RENDER_SERVICE_ID", "FLY_APP_NAME", "K_SERVICE", "DYNO", "AWS_EXECUTION_ENV"):
        os.environ.pop(m, None)
    with pytest.raises(RuntimeError, match="rediss"):
        assert_redis_url_tls("redis://h:1")


def test_local_process_forbidden_prod(monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("TBE_MULTI_TENANT", "1")
    from lumen.engine.services.live_deployment.local_process_driver import LocalProcessDriver
    with pytest.raises(RuntimeError, match="forbidden"):
        LocalProcessDriver()


def test_require_admin_source_fail_closed():
    """Source must refuse admin auth when rate limiter raises (no silent pass)."""
    src = Path("lumen/api/auth.py").read_text(encoding="utf-8")
    assert "admin_rate_limit_unavailable" in src
    assert "HTTPServiceUnavailable" in src
    # The old fail-open pattern must not remain after the limiter try block
    assert "except Exception:\n        pass\n\n    admin" not in src.replace("\r", "")


def test_no_direct_redis_from_url():
    import pathlib
    offenders = []
    for path in pathlib.Path("lumen").rglob("*.py"):
        if path.name == "redis_client.py":
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        if "Redis.from_url(" in text:
            offenders.append(str(path))
    assert not offenders, offenders


def test_crypto_token_min_32_in_prod(monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "production")
    for m in ("RAILWAY_ENVIRONMENT", "RENDER_SERVICE_ID", "FLY_APP_NAME", "K_SERVICE", "DYNO", "AWS_EXECUTION_ENV"):
        monkeypatch.delenv(m, raising=False)
    monkeypatch.setenv("TBE_TOKEN_SECRET", "short")
    from lumen.engine.services import crypto_tokens as ct
    # clear any cache of key
    with pytest.raises(RuntimeError, match="too short|required"):
        ct._raw_secret_material()
