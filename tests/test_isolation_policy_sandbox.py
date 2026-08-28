"""Isolation policy must accept Firecracker as strong isolation."""
from __future__ import annotations

from unittest import mock

import pytest


def test_strong_sandbox_available_true_when_fc_probes():
    from lumen.engine.services.sandbox_runtime.types import SandboxProbe
    with mock.patch(
        "lumen.engine.services.sandbox_runtime.select.probe_all",
        return_value=[SandboxProbe("firecracker", True, "ok", 100)],
    ):
        from lumen.engine.services.isolation_policy import strong_sandbox_available
        ok, reason = strong_sandbox_available()
        assert ok is True
        assert "firecracker" in reason


def test_require_strong_isolation_fails_closed(monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("TBE_MULTI_TENANT", "1")
    monkeypatch.delenv("TBE_ALLOW_LOCAL_PROCESS", raising=False)
    monkeypatch.delenv("TBE_FORCE_LOCAL_PROCESS", raising=False)
    from lumen.engine.services.sandbox_runtime.types import SandboxProbe
    with mock.patch(
        "lumen.engine.services.sandbox_runtime.select.probe_all",
        return_value=[
            SandboxProbe("firecracker", False, "no", 100),
            SandboxProbe("gvisor", False, "no", 85),
            SandboxProbe("dind", False, "no", 75),
            SandboxProbe("docker", False, "no", 50),
        ],
    ):
        from lumen.engine.services.isolation_policy import require_strong_isolation
        with pytest.raises(RuntimeError, match="strong_sandbox_required"):
            require_strong_isolation()


def test_decide_isolation_requires_strong_in_prod(monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("TBE_MULTI_TENANT", "1")
    from lumen.engine.services.isolation_policy import decide_isolation
    d = decide_isolation()
    assert d.require_strong_isolation is True
    assert d.allow_local is False
