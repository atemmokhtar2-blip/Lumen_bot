"""Sandbox runtime foundation tests."""
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


def test_probe_all_includes_gvisor():
    from telegram_bot_engine.services.sandbox_runtime import probe_all
    probes = probe_all()
    names = {p.name for p in probes}
    assert names >= {"firecracker", "gvisor", "dind", "docker"}


def test_policy_forbids_default_bridge():
    from telegram_bot_engine.services.sandbox_runtime.policy import assert_network_not_default_bridge
    with pytest.raises(RuntimeError, match="policy_violation"):
        assert_network_not_default_bridge("bridge")
    with pytest.raises(RuntimeError):
        assert_network_not_default_bridge("host")


def test_policy_forbids_docker_sock_mount():
    from telegram_bot_engine.services.sandbox_runtime.policy import assert_no_docker_sock_mount
    with pytest.raises(RuntimeError, match="docker.sock"):
        assert_no_docker_sock_mount(["-v", "/var/run/docker.sock:/var/run/docker.sock"])


def test_select_fails_closed_when_none(monkeypatch):
    monkeypatch.setenv("TBE_SANDBOX_BACKEND", "auto")
    from telegram_bot_engine.services.sandbox_runtime import select as sel
    with mock.patch.object(sel.FirecrackerSandboxBackend, "probe") as a, \
         mock.patch.object(sel.GVisorSandboxBackend, "probe") as g, \
         mock.patch.object(sel.DinDSandboxBackend, "probe") as b, \
         mock.patch.object(sel.DockerSandboxBackend, "probe") as c:
        from telegram_bot_engine.services.sandbox_runtime.types import SandboxProbe
        a.return_value = SandboxProbe("firecracker", False, "no", 100)
        g.return_value = SandboxProbe("gvisor", False, "no", 85)
        b.return_value = SandboxProbe("dind", False, "no", 75)
        c.return_value = SandboxProbe("docker", False, "no", 50)
        with pytest.raises(RuntimeError, match="no_sandbox_backend_available"):
            sel.select_sandbox_backend(require_available=True)


def test_dind_refuses_host_socket(monkeypatch):
    monkeypatch.setenv("TBE_DIND_HOST", "unix:///var/run/docker.sock")
    monkeypatch.delenv("TBE_DIND_ALLOW_HOST_SOCKET", raising=False)
    from telegram_bot_engine.services.sandbox_runtime.dind_backend import DinDSandboxBackend
    p = DinDSandboxBackend().probe()
    assert p.available is False


def test_seccomp_and_apparmor_files_exist():
    from pathlib import Path
    from telegram_bot_engine.services.sandbox_runtime.network import seccomp_profile_path
    p = seccomp_profile_path()
    assert p and os.path.isfile(p)
    aa = Path(__file__).resolve().parents[1] / "telegram_bot_engine/data/sandbox/apparmor-bot.profile"
    assert aa.is_file()


def test_load_policy_egress_hosts():
    from telegram_bot_engine.services.sandbox_runtime.policy import load_policy
    pol = load_policy()
    assert "api.telegram.org" in pol.egress_hosts
    assert pol.allow_docker_sock_in_bot is False
