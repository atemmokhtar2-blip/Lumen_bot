"""Sandbox runtime foundation tests (no live Docker required for unit probes)."""
from __future__ import annotations

import os
from unittest import mock

import pytest


def test_sandbox_types():
    from telegram_bot_engine.services.sandbox_runtime.types import SandboxSpec, SandboxHandle
    s = SandboxSpec(project_path="/tmp/x", bot_token="1:abc", user_id=1)
    assert s.user_id == 1
    h = SandboxHandle(backend="docker", deployment_id="d1", status="running")
    assert h.ok


def test_probe_all_returns_three():
    from telegram_bot_engine.services.sandbox_runtime import probe_all
    probes = probe_all()
    names = {p.name for p in probes}
    assert names == {"firecracker", "dind", "docker"}


def test_select_docker_when_forced(monkeypatch):
    from telegram_bot_engine.services.sandbox_runtime.docker_backend import DockerSandboxBackend
    monkeypatch.setenv("TBE_SANDBOX_BACKEND", "docker")
    with mock.patch.object(DockerSandboxBackend, "probe") as pr:
        from telegram_bot_engine.services.sandbox_runtime.types import SandboxProbe
        pr.return_value = SandboxProbe("docker", True, "ok", 50)
        from telegram_bot_engine.services.sandbox_runtime import select_sandbox_backend
        b, p = select_sandbox_backend(require_available=True)
        assert b.name == "docker"
        assert p.available


def test_select_fails_closed_when_none(monkeypatch):
    monkeypatch.setenv("TBE_SANDBOX_BACKEND", "auto")
    from telegram_bot_engine.services.sandbox_runtime import select as sel
    with mock.patch.object(sel.FirecrackerSandboxBackend, "probe") as a, \
         mock.patch.object(sel.DinDSandboxBackend, "probe") as b, \
         mock.patch.object(sel.DockerSandboxBackend, "probe") as c:
        from telegram_bot_engine.services.sandbox_runtime.types import SandboxProbe
        a.return_value = SandboxProbe("firecracker", False, "no", 100)
        b.return_value = SandboxProbe("dind", False, "no", 75)
        c.return_value = SandboxProbe("docker", False, "no", 50)
        with pytest.raises(RuntimeError, match="no_sandbox_backend_available"):
            sel.select_sandbox_backend(require_available=True)


def test_firecracker_probe_without_kvm():
    from telegram_bot_engine.services.sandbox_runtime.firecracker_backend import FirecrackerSandboxBackend
    p = FirecrackerSandboxBackend().probe()
    # On most CI hosts KVM is absent — must report unavailable, not pretend OK
    if not os.path.exists("/dev/kvm"):
        assert p.available is False


def test_dind_refuses_host_socket(monkeypatch):
    monkeypatch.setenv("TBE_DIND_HOST", "unix:///var/run/docker.sock")
    monkeypatch.delenv("TBE_DIND_ALLOW_HOST_SOCKET", raising=False)
    from telegram_bot_engine.services.sandbox_runtime.dind_backend import DinDSandboxBackend
    p = DinDSandboxBackend().probe()
    assert p.available is False
    assert "refusing" in p.reason or "docker.sock" in p.reason


def test_seccomp_profile_exists():
    from telegram_bot_engine.services.sandbox_runtime.network import seccomp_profile_path
    p = seccomp_profile_path()
    assert p and os.path.isfile(p)
