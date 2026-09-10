"""Phase D — Firecracker-only prod, edge WAF, CI gates."""
from __future__ import annotations

import os

import pytest


def test_assert_production_sandbox_refuses_docker(monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("TBE_MULTI_TENANT", "1")
    monkeypatch.setenv("TBE_SANDBOX_BACKEND", "docker")
    # Force production path via gate helper
    monkeypatch.setattr(
        "lumen.platform.prod_security_gate.is_production_runtime",
        lambda: True,
    )
    from lumen.platform.prod_security_gate import assert_production_sandbox_backend

    with pytest.raises(RuntimeError, match="Firecracker"):
        assert_production_sandbox_backend()


def test_assert_production_sandbox_allows_firecracker(monkeypatch):
    monkeypatch.setattr(
        "lumen.platform.prod_security_gate.is_production_runtime",
        lambda: True,
    )
    monkeypatch.setenv("TBE_SANDBOX_BACKEND", "firecracker")
    from lumen.platform.prod_security_gate import assert_production_sandbox_backend

    assert_production_sandbox_backend()  # no raise


def test_edge_waf_detects_cloudflare(monkeypatch):
    monkeypatch.setenv("TBE_REQUIRE_EDGE_WAF", "1")
    monkeypatch.setenv("TBE_EDGE_WAF_PROVIDER", "cloudflare")
    import importlib.util
    from pathlib import Path
    from types import SimpleNamespace

    path = Path("lumen/api/edge_waf.py")
    spec = importlib.util.spec_from_file_location("edge_waf_mod", path)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    req = SimpleNamespace(headers={"CF-Ray": "abc123"}, remote="1.2.3.4", path="/v1/me")
    assert mod._has_edge_mark(req) is True
    req2 = SimpleNamespace(headers={}, remote="1.2.3.4", path="/v1/me")
    assert mod._has_edge_mark(req2) is False


def test_edge_waf_secret_header(monkeypatch):
    monkeypatch.setenv("TBE_REQUIRE_EDGE_WAF", "1")
    monkeypatch.setenv("TBE_EDGE_WAF_SECRET", "edge-secret-xyz")
    import importlib.util
    from pathlib import Path
    from types import SimpleNamespace

    path = Path("lumen/api/edge_waf.py")
    spec = importlib.util.spec_from_file_location("edge_waf_mod2", path)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    req = SimpleNamespace(
        headers={"X-Lumen-Edge-Token": "edge-secret-xyz"},
        remote="1.2.3.4",
        path="/v1/me",
    )
    assert mod._has_edge_mark(req) is True


def test_host_service_has_phase_d_firecracker_gate():
    src = open("lumen/engine/services/hosting/service.py", encoding="utf-8").read()
    assert "Phase D — permanent host plane" in src
    assert "select_sandbox_backend" in src


def test_pip_audit_prefers_lockfile():
    src = open(".github/workflows/security.yml", encoding="utf-8").read()
    assert "requirements.lock" in src
    assert "pip-audit" in src
