"""Competitive isolation bar — fail-closed gates for multi-tenant hosting."""
from __future__ import annotations

from pathlib import Path
from unittest import mock

import pytest


def test_select_process_driver_returns_sandbox_in_prod(monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("TBE_MULTI_TENANT", "1")
    monkeypatch.delenv("TBE_ALLOW_LOCAL_PROCESS", raising=False)
    monkeypatch.delenv("TBE_FORCE_LOCAL_PROCESS", raising=False)
    from lumen.engine.services.sandbox_runtime.types import SandboxProbe
    with mock.patch(
        "lumen.engine.services.isolation_policy.strong_sandbox_available",
        return_value=(True, "firecracker:ok"),
    ), mock.patch(
        "lumen.engine.services.isolation_policy.require_strong_isolation",
    ):
        from lumen.engine.services.isolation_policy import select_process_driver
        driver, decision = select_process_driver()
        assert driver.name == "sandbox_runtime"
        assert decision.require_strong_isolation is True


def test_local_process_defaults_deny_on_policy_error():
    src = Path("lumen/engine/engines/generators/live_deployment/local_process_driver.py").read_text()
    assert 'or "0"' in src or "or '0'" in src
    assert 'TBE_LOCAL_FALLBACK_WHEN_NO_DOCKER") or "1"' not in src


def test_diagnose_reads_fc_logs_source():
    src = Path("lumen/engine/services/hosting/service.py").read_text()
    assert "FirecrackerSandboxBackend().logs" in src


def test_fc_balloon_configured():
    src = Path("lumen/engine/services/sandbox_runtime/firecracker_backend.py").read_text()
    assert "/balloon" in src
    assert "TBE_FC_BALLOON" in src
