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
    """Dev auto: no backend available → no_sandbox_backend_available."""
    monkeypatch.setenv("ENVIRONMENT", "dev")
    monkeypatch.setenv("TBE_MULTI_TENANT", "0")
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
    monkeypatch.setenv("TBE_MULTI_TENANT", "0")
    monkeypatch.setenv("TBE_FC_ALLOW_NO_JAILER", "1")
    monkeypatch.setenv("TBE_FC_REQUIRE_JAILER", "0")
    monkeypatch.setenv("TBE_FC_AUTO_NET", "0")
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
        # AUTO_NET default needs iproute2; without it probe fails closed
        assert (
            "TBE_FC_TAP" in p.reason
            or "NETNS" in p.reason
            or "iproute2" in p.reason
            or "auto_net" in p.reason.lower()
            or "fc_network" in p.reason.lower()
            or "AUTO_NET" in p.reason
        )


def test_firecracker_bootargs_token_forbidden_in_production(monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("FORCE_PRODUCTION", "1")
    monkeypatch.setenv("TBE_FC_AUTO_NET", "0")
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


def test_production_forces_firecracker_rejects_docker(monkeypatch):
    """Production/multi-tenant must not select docker even if requested."""
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("TBE_MULTI_TENANT", "1")
    monkeypatch.setenv("TBE_SANDBOX_BACKEND", "docker")
    from lumen.engine.services.sandbox_runtime import select as sel
    with pytest.raises(RuntimeError, match="production_requires_firecracker"):
        sel.select_sandbox_backend(require_available=False)


def test_production_auto_uses_firecracker_only(monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("TBE_MULTI_TENANT", "1")
    monkeypatch.setenv("TBE_SANDBOX_BACKEND", "auto")
    from lumen.engine.services.sandbox_runtime import select as sel
    from lumen.engine.services.sandbox_runtime.types import SandboxProbe
    with mock.patch.object(sel.FirecrackerSandboxBackend, "probe") as fc, \
         mock.patch.object(sel.DockerSandboxBackend, "probe") as dk:
        fc.return_value = SandboxProbe("firecracker", True, "ok", 100)
        dk.return_value = SandboxProbe("docker", True, "ok", 50)
        b, p = sel.select_sandbox_backend(require_available=True)
        assert b.name == "firecracker"
        assert p.available is True
        dk.assert_not_called()


def test_production_fails_when_firecracker_down_no_docker_fallback(monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("TBE_MULTI_TENANT", "1")
    monkeypatch.setenv("TBE_SANDBOX_BACKEND", "auto")
    from lumen.engine.services.sandbox_runtime import select as sel
    from lumen.engine.services.sandbox_runtime.types import SandboxProbe
    with mock.patch.object(sel.FirecrackerSandboxBackend, "probe") as fc, \
         mock.patch.object(sel.DockerSandboxBackend, "probe") as dk, \
         mock.patch.object(sel.GVisorSandboxBackend, "probe") as gv:
        fc.return_value = SandboxProbe("firecracker", False, "kvm_unavailable", 100)
        dk.return_value = SandboxProbe("docker", True, "ok", 50)
        gv.return_value = SandboxProbe("gvisor", True, "ok", 85)
        with pytest.raises(RuntimeError, match="sandbox_backend_unavailable:firecracker"):
            sel.select_sandbox_backend(require_available=True)
        dk.assert_not_called()
        gv.assert_not_called()


def test_dev_allows_explicit_docker(monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "dev")
    monkeypatch.setenv("TBE_MULTI_TENANT", "0")
    monkeypatch.setenv("TBE_SANDBOX_BACKEND", "docker")
    from lumen.engine.services.sandbox_runtime import select as sel
    from lumen.engine.services.sandbox_runtime.types import SandboxProbe
    with mock.patch.object(sel.DockerSandboxBackend, "probe") as dk:
        dk.return_value = SandboxProbe("docker", True, "ok", 50)
        b, p = sel.select_sandbox_backend(require_available=True)
        assert b.name == "docker"


def test_is_production_sandbox_path(monkeypatch):
    from lumen.engine.services.sandbox_runtime.select import is_production_sandbox_path
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("TBE_MULTI_TENANT", "1")
    assert is_production_sandbox_path() is True
    monkeypatch.setenv("ENVIRONMENT", "dev")
    monkeypatch.setenv("TBE_MULTI_TENANT", "0")
    assert is_production_sandbox_path() is False


def test_market_gate_rejects_docker_commercial(monkeypatch):
    monkeypatch.setenv("TBE_MARKET_GATE", "1")
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("TBE_SANDBOX_BACKEND", "docker")
    monkeypatch.setenv("TBE_TOKEN_SECRET", "x" * 40)
    monkeypatch.setenv("TBE_SCALE_MODE", "1")
    monkeypatch.setenv("TBE_DATABASE_URL", "postgresql://u:p@localhost/db")
    monkeypatch.setenv("TBE_ALLOW_LOCAL_PROCESS", "0")
    from lumen.engine.services.hosting.market_gate import evaluate_market_gate
    g = evaluate_market_gate()
    assert g.ok is False
    assert g.track == "rejected"
    assert any("Firecracker" in m or "firecracker" in m.lower() or "غير مقبول" in m for m in g.missing)


def test_fc_require_jailer_forced_in_production(monkeypatch):
    """TBE_FC_REQUIRE_JAILER=0 must not disable jailer on production path."""
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("TBE_MULTI_TENANT", "1")
    monkeypatch.setenv("TBE_FC_REQUIRE_JAILER", "0")
    monkeypatch.delenv("TBE_FC_ALLOW_NO_JAILER", raising=False)
    from lumen.engine.services.sandbox_runtime import firecracker_backend as fc
    assert fc._require_jailer() is True


def test_fc_allow_no_jailer_only_in_dev(monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "dev")
    monkeypatch.setenv("TBE_MULTI_TENANT", "0")
    monkeypatch.setenv("TBE_FC_ALLOW_NO_JAILER", "1")
    from lumen.engine.services.sandbox_runtime import firecracker_backend as fc
    assert fc._require_jailer() is False


def test_fc_probe_rejects_allow_no_net_in_production(monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("TBE_MULTI_TENANT", "1")
    monkeypatch.setenv("TBE_FC_ALLOW_NO_NET", "1")
    monkeypatch.setenv("TBE_FC_KERNEL", "/tmp/k")
    monkeypatch.setenv("TBE_FC_ROOTFS", "/tmp/r")
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
        p = FirecrackerSandboxBackend().probe()
        assert p.available is False
        assert "ALLOW_NO_NET" in p.reason or "no_net" in p.reason.lower()


def test_fc_probe_rejects_token_in_bootargs_in_production(monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("TBE_MULTI_TENANT", "1")
    monkeypatch.setenv("TBE_FC_TOKEN_IN_BOOTARGS", "1")
    monkeypatch.setenv("TBE_FC_AUTO_NET", "1")
    monkeypatch.setenv("TBE_FC_KERNEL", "/tmp/k")
    monkeypatch.setenv("TBE_FC_ROOTFS", "/tmp/r")
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
    ), mock.patch("os.path.isfile", return_value=True), mock.patch(
        "lumen.engine.services.sandbox_runtime.fc_network.ip_available",
        return_value=True,
    ):
        from lumen.engine.services.sandbox_runtime.firecracker_backend import (
            FirecrackerSandboxBackend,
        )
        p = FirecrackerSandboxBackend().probe()
        assert p.available is False
        assert "TOKEN_IN_BOOTARGS" in p.reason or "bootargs" in p.reason.lower()

def test_fc_tap_egress_rejects_invalid_tap():
    from lumen.engine.services.sandbox_runtime.fc_network import apply_fc_tap_egress
    r = apply_fc_tap_egress("")
    assert r["ok"] is False
    assert "invalid_tap" in r["errors"] or "iptables_not_found" in r["errors"]


def test_guest_agent_files_exist():
    from lumen.engine.services.sandbox_runtime.guest_agent import SUPERVISOR_PATH, BOOT_SH_PATH
    assert SUPERVISOR_PATH.is_file()
    assert "lumen-guest-ready" in SUPERVISOR_PATH.read_text(encoding="utf-8")
    assert "lumen-bot-started" in SUPERVISOR_PATH.read_text(encoding="utf-8")
    assert BOOT_SH_PATH.is_file()


def test_inject_guest_agent_into_project(tmp_path):
    from lumen.engine.services.sandbox_runtime.firecracker_backend import _inject_guest_agent
    proj = tmp_path / "bot"
    proj.mkdir()
    (proj / "main.py").write_text("print(1)\n")
    _inject_guest_agent(proj)
    assert (proj / ".lumen_guest" / "supervisor.py").is_file()
    assert (proj / ".lumen_guest" / "lumen-guest-boot.sh").is_file()


def test_wait_for_bot_health_reads_markers(tmp_path, monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("TBE_MULTI_TENANT", "1")
    log = tmp_path / "vm.log"
    log.write_text("boot\nlumen-guest-ready\nlumen-bot-started entry=main.py\n")
    from lumen.engine.services.sandbox_runtime.firecracker_backend import FirecrackerSandboxBackend
    b = FirecrackerSandboxBackend()
    meta = {"log": str(log), "pid": 0}
    ok, reason = b._wait_for_bot_health("fc-test", meta, timeout_sec=2)
    assert ok is True
    assert "bot_marker" in reason


def test_wait_for_bot_health_fatal(tmp_path):
    log = tmp_path / "vm.log"
    log.write_text("lumen-bot-fatal token_missing\n")
    from lumen.engine.services.sandbox_runtime.firecracker_backend import FirecrackerSandboxBackend
    b = FirecrackerSandboxBackend()
    ok, reason = b._wait_for_bot_health("fc-test", {"log": str(log), "pid": 0}, timeout_sec=2)
    assert ok is False
    assert "fatal" in reason

def test_fc_status_fatal_not_running(tmp_path, monkeypatch):
    import json, os
    from lumen.engine.services.sandbox_runtime.firecracker_backend import FirecrackerSandboxBackend
    b = FirecrackerSandboxBackend()
    vm_id = "fc-0-testhealth"
    log = tmp_path / "vm.log"
    log.write_text("lumen-guest-ready\nlumen-bot-fatal token_missing\n")
    meta = {"pid": os.getpid(), "log": str(log), "vm_id": vm_id}
    # write meta where backend expects
    b._state_dir.mkdir(parents=True, exist_ok=True)
    (b._state_dir / f"{vm_id}.json").write_text(json.dumps(meta), encoding="utf-8")
    st = b.status(vm_id)
    assert st.status == "failed"
    assert st.meta.get("bot_fatal") is True

def test_warm_jailed_none_without_pool(tmp_path, monkeypatch):
    monkeypatch.setenv("TBE_FC_WARM_POOL", "1")
    monkeypatch.setenv("TBE_FC_SNAPSHOT_DIR", str(tmp_path / "empty_pool"))
    from lumen.engine.services.sandbox_runtime.fc_warm_start import try_warm_start_jailed
    r = try_warm_start_jailed(
        firecracker_bin="/bin/false",
        jailer_bin="/bin/false",
        vm_id="fc-warm-test",
        uid=10000,
        gid=10000,
        chroot_base=tmp_path / "jail",
        log_path=tmp_path / "w.log",
    )
    assert r is None
