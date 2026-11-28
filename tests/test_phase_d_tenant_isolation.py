"""Phase D — multi-tenant isolation + real WAF + docker ACK."""
from __future__ import annotations

import pytest


def test_redis_keys_namespaced():
    from lumen.platform.tenant_isolation import host_instance_redis_key, host_user_index_key
    key_a = host_instance_redis_key("host-1", tenant_id="ten_abc")
    key_b = host_instance_redis_key("host-1", tenant_id="ten/a_bc")
    assert key_a.startswith("lumen:host:t:t_")
    assert key_a != key_b
    assert host_instance_redis_key("host-1", tenant_id="") == "lumen:host:inst:host-1"


def test_assert_instance_owner(monkeypatch):
    from types import SimpleNamespace
    from lumen.platform.tenant_isolation import assert_instance_owner

    inst = SimpleNamespace(user_id=7, tenant_id="ten_a")
    assert assert_instance_owner(inst, user_id=7, tenant_id="ten_a")
    assert not assert_instance_owner(inst, user_id=8, tenant_id="ten_a")
    assert not assert_instance_owner(inst, user_id=7, tenant_id="ten_b")
    # Matching numeric surrogate alone must not expose a tenant-owned instance
    # through a Telegram/user-scoped listing.
    assert not assert_instance_owner(inst, user_id=7)
    monkeypatch.setattr(
        "lumen.platform.prod_security_gate.is_production_runtime", lambda: True
    )
    legacy = SimpleNamespace(user_id=7, tenant_id="")
    assert not assert_instance_owner(legacy, user_id=7, tenant_id="ten_a")


def test_fc_state_dir_per_user(tmp_path, monkeypatch):
    monkeypatch.setenv("TBE_FC_STATE_DIR", str(tmp_path / "fc"))
    monkeypatch.setenv("ENVIRONMENT", "dev")
    from lumen.platform.tenant_isolation import firecracker_state_dir
    d1 = firecracker_state_dir(user_id=1, tenant_id="ten_a")
    d2 = firecracker_state_dir(user_id=2, tenant_id="ten_a")
    assert d1 != d2


def test_verify_respects_base_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "dev")
    from lumen.engine.services.user_sandbox import get_user_sandbox
    from lumen.platform.tenant_isolation import verify_project_under_owner

    sb = get_user_sandbox(99, tmp_path)
    sb.ensure()
    proj = sb.new_project_dir(label="p")
    got = verify_project_under_owner(user_id=99, project_path=str(proj), base_dir=tmp_path)
    assert str(got).startswith(str(tmp_path))


def test_waf_prod_requires_secret(monkeypatch):
    import importlib.util
    from pathlib import Path
    from types import SimpleNamespace

    path = Path("lumen/api/edge_waf.py")
    spec = importlib.util.spec_from_file_location("edge_waf_real", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    monkeypatch.setenv("TBE_REQUIRE_EDGE_WAF", "1")
    monkeypatch.setenv("TBE_EDGE_WAF_SECRET", "super-secret-edge-token-32chars!!")
    monkeypatch.setattr(
        "lumen.platform.prod_security_gate.is_production_runtime", lambda: True
    )
    # CF-Ray alone insufficient
    req = SimpleNamespace(headers={"CF-Ray": "abc"}, remote="1.2.3.4", path="/v1/me")
    assert mod._has_edge_mark(req) is False
    req2 = SimpleNamespace(
        headers={"X-Lumen-Edge-Token": "super-secret-edge-token-32chars!!"},
        remote="1.2.3.4",
        path="/v1/me",
    )
    assert mod._has_edge_mark(req2) is True


def test_docker_ack_required_in_prod_gate(monkeypatch):
    monkeypatch.setattr(
        "lumen.platform.prod_security_gate.is_production_runtime", lambda: True
    )
    monkeypatch.setenv("TBE_MULTI_TENANT", "1")
    monkeypatch.setenv("TBE_SANDBOX_BACKEND", "docker")
    monkeypatch.delenv("TBE_DOCKER_ISOLATION_ACK", raising=False)
    from lumen.platform.prod_security_gate import assert_production_sandbox_backend
    import pytest
    with pytest.raises(RuntimeError, match="DOCKER_ISOLATION_ACK"):
        assert_production_sandbox_backend()
    monkeypatch.setenv(
        "TBE_DOCKER_ISOLATION_ACK", "I_ACCEPT_ISOLATED_DOCKER_NOT_FIRECRACKER"
    )
    assert_production_sandbox_backend()


def test_hosts_api_passes_tenant_id():
    src = open("lumen/api/routes/hosts.py", encoding="utf-8").read()
    assert "tenant_id=tenant.tenant_id" in src



def test_verify_uses_tenant_sandbox_not_numeric_user_sandbox(tmp_path, monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "dev")
    from lumen.engine.services.user_sandbox import get_tenant_sandbox, get_user_sandbox
    from lumen.platform.tenant_isolation import verify_project_under_owner

    tenant_sandbox = get_tenant_sandbox("tenant/acme", tmp_path)
    tenant_project = tenant_sandbox.new_project_dir(label="tenant-project")
    verified = verify_project_under_owner(
        user_id=7,
        tenant_id="tenant/acme",
        project_path=str(tenant_project),
        base_dir=tmp_path,
    )
    assert verified == tenant_project.resolve()

    user_sandbox = get_user_sandbox(7, tmp_path)
    user_project = user_sandbox.new_project_dir(label="user-project")
    with pytest.raises(ValueError, match="outside_sandbox"):
        verify_project_under_owner(
            user_id=7,
            tenant_id="tenant/acme",
            project_path=str(user_project),
            base_dir=tmp_path,
        )


def test_tenant_key_and_firecracker_namespaces_are_collision_resistant(tmp_path, monkeypatch):
    from lumen.platform.tenant_isolation import (
        safe_tenant_segment,
        firecracker_state_dir,
        host_user_index_key,
    )

    assert safe_tenant_segment("a/b") != safe_tenant_segment("a_b")
    assert host_user_index_key(5, tenant_id="a/b") != host_user_index_key(5, tenant_id="a_b")

    monkeypatch.setenv("TBE_FC_STATE_DIR", str(tmp_path / "fc"))
    one = firecracker_state_dir(user_id=5, tenant_id="a/b")
    two = firecracker_state_dir(user_id=5, tenant_id="a_b")
    assert one != two



def test_firecracker_state_dirs_are_owner_scoped(tmp_path, monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "dev")
    monkeypatch.setenv("TBE_MULTI_TENANT", "0")
    monkeypatch.setenv("TBE_FC_STATE_DIR", str(tmp_path / "fc"))
    from lumen.engine.services.sandbox_runtime.firecracker_backend import FirecrackerSandboxBackend

    a = FirecrackerSandboxBackend(user_id=7, tenant_id="tenant/a")
    b = FirecrackerSandboxBackend(user_id=7, tenant_id="tenant_a")
    assert a._state_dir != b._state_dir
    assert a._state_dir.is_relative_to(tmp_path / "fc")
    assert b._state_dir.is_relative_to(tmp_path / "fc")


def test_firecracker_lifecycle_requires_owner_context_in_production(tmp_path, monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("TBE_MULTI_TENANT", "1")
    monkeypatch.setenv("TBE_FC_STATE_DIR", str(tmp_path / "fc"))
    from lumen.engine.services.sandbox_runtime.firecracker_backend import FirecrackerSandboxBackend
    from lumen.engine.services.sandbox_runtime.types import SandboxSpec

    probe_backend = FirecrackerSandboxBackend()
    with pytest.raises(RuntimeError, match="firecracker_owner_context_required"):
        probe_backend.start(SandboxSpec(project_path=str(tmp_path), bot_token="x"))

    owned = FirecrackerSandboxBackend(user_id=7, tenant_id="tenant/acme")
    assert owned._state_dir != probe_backend._state_dir


def test_host_service_list_isolates_tenant_from_telegram_same_numeric_uid(monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "test")
    from lumen.engine.services.hosting.service import HostingService, HostInstance

    service = HostingService.__new__(HostingService)
    service._instances = {
        "tenant": HostInstance(
            instance_id="tenant",
            user_id=123,
            tenant_id="tenant/acme",
            project_path="/tmp/tenant",
            status="running",
        ),
        "telegram": HostInstance(
            instance_id="telegram",
            user_id=123,
            tenant_id="",
            project_path="/tmp/telegram",
            status="running",
        ),
    }
    assert [x.instance_id for x in service.list_for_user(123)] == ["telegram"]
    assert [x.instance_id for x in service.list_for_user(123, tenant_id="tenant/acme")] == ["tenant"]



def test_http_host_requires_tenant_binding_in_production(tmp_path, monkeypatch):
    monkeypatch.setenv("TBE_MULTI_TENANT", "1")
    from lumen.engine.services.hosting.service import HostingService
    monkeypatch.setattr(
        "lumen.platform.prod_security_gate.is_production_runtime",
        lambda: True,
    )
    service = HostingService.__new__(HostingService)
    service.output_root = tmp_path

    result = service.start_http_public(
        user_id=5,
        project_path=tmp_path,
        tenant_id="",
    )
    assert result.ok is False
    assert "tenant_id_required" in result.message
