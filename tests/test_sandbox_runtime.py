"""Sandbox runtime foundation tests — fail-closed gaps + Firecracker production path."""
from __future__ import annotations

import os
from pathlib import Path
from unittest import mock

import pytest


def test_sandbox_types():
    from lumen.engine.services.sandbox_runtime.types import SandboxSpec, SandboxHandle
    s = SandboxSpec(project_path="/tmp/x", bot_token="1:abc", user_id=1)
    assert s.user_id == 1
    h = SandboxHandle(backend="docker", deployment_id="d1", status="running")
    assert h.ok


def test_probe_all_includes_gvisor():
    from lumen.engine.services.sandbox_runtime import probe_all
    probes = probe_all()
    names = {p.name for p in probes}
    assert names >= {"firecracker", "gvisor", "dind", "docker"}


def test_policy_forbids_default_bridge():
    from lumen.engine.services.sandbox_runtime.policy import assert_network_not_default_bridge
    with pytest.raises(RuntimeError, match="policy_violation"):
        assert_network_not_default_bridge("bridge")
    with pytest.raises(RuntimeError):
        assert_network_not_default_bridge("host")


def test_policy_forbids_docker_sock_mount():
    from lumen.engine.services.sandbox_runtime.policy import assert_no_docker_sock_mount
    with pytest.raises(RuntimeError, match="docker.sock"):
        assert_no_docker_sock_mount(["-v", "/var/run/docker.sock:/var/run/docker.sock"])


def test_select_fails_closed_when_none(monkeypatch):
    monkeypatch.setenv("TBE_SANDBOX_BACKEND", "auto")
    from lumen.engine.services.sandbox_runtime import select as sel
    with mock.patch.object(sel.FirecrackerSandboxBackend, "probe") as a, \
         mock.patch.object(sel.GVisorSandboxBackend, "probe") as g, \
         mock.patch.object(sel.DinDSandboxBackend, "probe") as b, \
         mock.patch.object(sel.DockerSandboxBackend, "probe") as c:
        from lumen.engine.services.sandbox_runtime.types import SandboxProbe
        a.return_value = SandboxProbe("firecracker", False, "no", 100)
        g.return_value = SandboxProbe("gvisor", False, "no", 85)
        b.return_value = SandboxProbe("dind", False, "no", 75)
        c.return_value = SandboxProbe("docker", False, "no", 50)
        with pytest.raises(RuntimeError, match="no_sandbox_backend_available"):
            sel.select_sandbox_backend(require_available=True)


def test_dind_refuses_host_socket(monkeypatch):
    monkeypatch.setenv("TBE_DIND_HOST", "unix:///var/run/docker.sock")
    monkeypatch.delenv("TBE_DIND_ALLOW_HOST_SOCKET", raising=False)
    from lumen.engine.services.sandbox_runtime.dind_backend import DinDSandboxBackend
    p = DinDSandboxBackend().probe()
    assert p.available is False


def test_firecracker_probe_requires_kvm(monkeypatch):
    with mock.patch(
        "lumen.engine.services.sandbox_runtime.firecracker_backend._kvm_ok",
        return_value=False,
    ):
        from lumen.engine.services.sandbox_runtime.firecracker_backend import (
            FirecrackerSandboxBackend,
        )
        p = FirecrackerSandboxBackend().probe()
        assert p.available is False
        assert "kvm" in p.reason.lower()


def test_firecracker_probe_requires_jailer_in_prod(monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("TBE_FC_REQUIRE_JAILER", "1")
    monkeypatch.setenv("TBE_FC_KERNEL", "/tmp/k")
    monkeypatch.setenv("TBE_FC_ROOTFS", "/tmp/r")
    monkeypatch.setenv("TBE_FC_TAP", "tap0")
    monkeypatch.delenv("TBE_FC_ALLOW_NO_JAILER", raising=False)
    Path("/tmp/k").write_text("k")
    Path("/tmp/r").write_text("r")
    with mock.patch(
        "lumen.engine.services.sandbox_runtime.firecracker_backend._kvm_ok",
        return_value=True,
    ), mock.patch(
        "lumen.engine.services.sandbox_runtime.firecracker_backend._bin",
        return_value="/usr/bin/firecracker",
    ), mock.patch(
        "lumen.engine.services.sandbox_runtime.firecracker_backend._jailer_bin",
        return_value="",
    ), mock.patch("os.path.isfile", return_value=True):
        from lumen.engine.services.sandbox_runtime.firecracker_backend import (
            FirecrackerSandboxBackend,
        )
        p = FirecrackerSandboxBackend().probe()
        assert p.available is False
        assert "jailer" in p.reason.lower()


def test_firecracker_probe_requires_tap(monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "dev")
    monkeypatch.setenv("TBE_FC_ALLOW_NO_JAILER", "1")
    monkeypatch.setenv("TBE_FC_REQUIRE_JAILER", "0")
    monkeypatch.setenv("TBE_FC_KERNEL", "/tmp/k")
    monkeypatch.setenv("TBE_FC_ROOTFS", "/tmp/r")
    monkeypatch.delenv("TBE_FC_TAP", raising=False)
    monkeypatch.delenv("TBE_FC_NETNS", raising=False)
    monkeypatch.delenv("TBE_FC_ALLOW_NO_NET", raising=False)
    Path("/tmp/k").write_text("k")
    Path("/tmp/r").write_text("r")
    with mock.patch(
        "lumen.engine.services.sandbox_runtime.firecracker_backend._kvm_ok",
        return_value=True,
    ), mock.patch(
        "lumen.engine.services.sandbox_runtime.firecracker_backend._bin",
        return_value="/usr/bin/firecracker",
    ), mock.patch("os.path.isfile", return_value=True):
        from lumen.engine.services.sandbox_runtime.firecracker_backend import (
            FirecrackerSandboxBackend,
        )
        p = FirecrackerSandboxBackend().probe()
        assert p.available is False
        assert "TBE_FC_TAP" in p.reason or "NETNS" in p.reason


def test_firecracker_bootargs_token_forbidden_in_production(monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("FORCE_PRODUCTION", "1")
    monkeypatch.setenv("TBE_FC_TAP", "tap0")
    monkeypatch.setenv("TBE_FC_KERNEL", "/tmp/k")
    monkeypatch.setenv("TBE_FC_ROOTFS", "/tmp/r")
    monkeypatch.setenv("TBE_FC_TOKEN_IN_BOOTARGS", "1")
    monkeypatch.setenv("TBE_FC_REQUIRE_JAILER", "0")
    monkeypatch.setenv("TBE_FC_ALLOW_NO_JAILER", "1")
    Path("/tmp/k").write_text("k")
    Path("/tmp/r").write_text("r")
    with mock.patch(
        "lumen.engine.services.sandbox_runtime.firecracker_backend._kvm_ok",
        return_value=True,
    ), mock.patch(
        "lumen.engine.services.sandbox_runtime.firecracker_backend._bin",
        return_value="/usr/bin/firecracker",
    ), mock.patch(
        "lumen.engine.services.sandbox_runtime.firecracker_backend._jailer_bin",
        return_value="/usr/bin/jailer",
    ), mock.patch("os.path.isfile", return_value=True):
        from lumen.engine.services.sandbox_runtime.firecracker_backend import (
            FirecrackerSandboxBackend,
        )
        from lumen.engine.services.sandbox_runtime.types import SandboxSpec
        h = FirecrackerSandboxBackend().start(
            SandboxSpec(project_path="/tmp/p", bot_token="1:tok", user_id=1)
        )
        assert h.status == "failed"
        assert "bootargs" in h.message.lower() or "production" in h.message.lower()


def test_firecracker_stable_uid_range():
    from lumen.engine.services.sandbox_runtime.firecracker_backend import _stable_vm_ids, _FC_UID_BASE
    u1, g1 = _stable_vm_ids(42, "fc-42-abc")
    u2, g2 = _stable_vm_ids(42, "fc-42-abc")
    assert u1 == u2 == g1 == g2
    assert u1 >= _FC_UID_BASE
    u3, _ = _stable_vm_ids(99, "fc-99-xyz")
    assert u3 != u1


def test_guest_mac_format():
    from lumen.engine.services.sandbox_runtime.firecracker_backend import FirecrackerSandboxBackend
    mac = FirecrackerSandboxBackend._guest_mac("fc-1-deadbeef")
    parts = mac.split(":")
    assert len(parts) == 6
    assert parts[0] == "AA"
    assert parts[1] == "FC"


def test_egress_strict_raises_when_iptables_fails(monkeypatch):
    monkeypatch.setenv("TBE_EGRESS_MODE", "strict")
    monkeypatch.setenv("TBE_EGRESS_IPTABLES", "1")
    from lumen.engine.services.sandbox_runtime import egress as eg
    with mock.patch.object(eg, "apply_egress_iptables", return_value={"ok": False, "errors": ["x"]}):
        with mock.patch(
            "lumen.engine.services.sandbox_runtime.network.ensure_egress_network",
            return_value="tbe-egress",
        ), mock.patch(
            "lumen.engine.services.sandbox_runtime.network.network_exists",
            return_value=True,
        ):
            with pytest.raises(RuntimeError, match="egress_strict_failed"):
                eg.harden_network("tbe-egress")


def test_load_policy_egress_hosts():
    from lumen.engine.services.sandbox_runtime.policy import load_policy
    pol = load_policy()
    assert "api.telegram.org" in pol.egress_hosts
    assert pol.allow_docker_sock_in_bot is False
