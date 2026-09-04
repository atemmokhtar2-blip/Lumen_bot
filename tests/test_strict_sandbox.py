
import os
import pytest


def test_assert_unsafe_flags_in_production(monkeypatch):
    from lumen.engine.services.sandbox_runtime.strict import assert_no_unsafe_sandbox_flags
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("TBE_UNSAFE_ALLOW_HOST_PROCESS", "1")
    with pytest.raises(RuntimeError, match="production_unsafe"):
        assert_no_unsafe_sandbox_flags()


def test_assert_ok_without_unsafe(monkeypatch):
    from lumen.engine.services.sandbox_runtime.strict import assert_no_unsafe_sandbox_flags
    monkeypatch.setenv("ENVIRONMENT", "production")
    for k in list(os.environ):
        if k.startswith("TBE_") and "ALLOW" in k:
            monkeypatch.delenv(k, raising=False)
    monkeypatch.delenv("TBE_SANDBOX_BACKEND", raising=False)
    assert_no_unsafe_sandbox_flags()  # should not raise


def test_market_gate_cannot_skip_in_prod(monkeypatch):
    from lumen.engine.services.hosting.market_gate import market_gate_enabled
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("TBE_MARKET_GATE", "0")
    assert market_gate_enabled() is True


def test_resource_defaults_clamped():
    from lumen.hosting.project_manifest import default_resources_from_env
    r = default_resources_from_env()
    assert r.memory_mb <= 256
    assert r.cpu <= 0.5
