"""Sandbox runtime foundation tests — fail-closed gaps."""
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


def test_firecracker_probe_requires_tap(monkeypatch):
    monkeypatch.delenv("TBE_FC_TAP", raising=False)
    monkeypatch.delenv("TBE_FC_ALLOW_NO_NET", raising=False)
    monkeypatch.setenv("TBE_FC_KERNEL", "/tmp/fake_kernel")
    monkeypatch.setenv("TBE_FC_ROOTFS", "/tmp/fake_rootfs")
    from pathlib import Path
    Path("/tmp/fake_kernel").write_text("x")
    Path("/tmp/fake_rootfs").write_text("x")
    with mock.patch(
        "telegram_bot_engine.services.sandbox_runtime.firecracker_backend._kvm_ok",
        return_value=True,
    ), mock.patch(
        "telegram_bot_engine.services.sandbox_runtime.firecracker_backend._bin",
        return_value="/usr/bin/firecracker",
    ), mock.patch("os.path.isfile", return_value=True):
        from telegram_bot_engine.services.sandbox_runtime.firecracker_backend import (
            FirecrackerSandboxBackend,
        )
        p = FirecrackerSandboxBackend().probe()
        assert p.available is False
        assert "TBE_FC_TAP" in p.reason


def test_firecracker_start_requires_token_path(monkeypatch):
    monkeypatch.setenv("TBE_FC_TAP", "tap0")
    monkeypatch.setenv("TBE_FC_KERNEL", "/tmp/k")
    monkeypatch.setenv("TBE_FC_ROOTFS", "/tmp/r")
    monkeypatch.delenv("TBE_FC_TOKEN_DRIVE", raising=False)
    monkeypatch.delenv("TBE_FC_TOKEN_IN_BOOTARGS", raising=False)
    from pathlib import Path
    Path("/tmp/k").write_text("k")
    Path("/tmp/r").write_text("r")
    with mock.patch(
        "telegram_bot_engine.services.sandbox_runtime.firecracker_backend._kvm_ok",
        return_value=True,
    ), mock.patch(
        "telegram_bot_engine.services.sandbox_runtime.firecracker_backend._bin",
        return_value="/usr/bin/firecracker",
    ), mock.patch("os.path.isfile", return_value=True), mock.patch(
        "shutil.which", return_value="/usr/bin/curl"
    ):
        from telegram_bot_engine.services.sandbox_runtime.firecracker_backend import (
            FirecrackerSandboxBackend,
        )
        from telegram_bot_engine.services.sandbox_runtime.types import SandboxSpec
        h = FirecrackerSandboxBackend().start(
            SandboxSpec(project_path="/tmp/p", bot_token="1:tok", user_id=1)
        )
        assert h.status == "failed"
        assert "token" in h.message.lower()


def test_egress_strict_raises_when_iptables_fails(monkeypatch):
    monkeypatch.setenv("TBE_EGRESS_MODE", "strict")
    monkeypatch.setenv("TBE_EGRESS_IPTABLES", "1")
    from telegram_bot_engine.services.sandbox_runtime import egress as eg
    with mock.patch.object(eg, "apply_egress_iptables", return_value={"ok": False, "errors": ["x"]}):
        with mock.patch.object(eg, "ensure_egress_network", create=True):
            # patch network module used inside harden
            with mock.patch(
                "telegram_bot_engine.services.sandbox_runtime.network.ensure_egress_network",
                return_value="tbe-egress",
            ), mock.patch(
                "telegram_bot_engine.services.sandbox_runtime.network.network_exists",
                return_value=True,
            ):
                with pytest.raises(RuntimeError, match="egress_strict_failed"):
                    eg.harden_network("tbe-egress")


def test_load_policy_egress_hosts():
    from telegram_bot_engine.services.sandbox_runtime.policy import load_policy
    pol = load_policy()
    assert "api.telegram.org" in pol.egress_hosts
    assert pol.allow_docker_sock_in_bot is False
