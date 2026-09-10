"""Phase D — multi-tenant isolation + real WAF + docker ACK."""
from __future__ import annotations

import pytest


def test_redis_keys_namespaced():
    from lumen.platform.tenant_isolation import host_instance_redis_key, host_user_index_key
    assert "t:ten_abc" in host_instance_redis_key("host-1", tenant_id="ten_abc")
    assert host_instance_redis_key("host-1", tenant_id="") == "lumen:host:inst:host-1"


def test_assert_instance_owner(monkeypatch):
    from types import SimpleNamespace
    from lumen.platform.tenant_isolation import assert_instance_owner

    inst = SimpleNamespace(user_id=7, tenant_id="ten_a")
    assert assert_instance_owner(inst, user_id=7, tenant_id="ten_a")
    assert not assert_instance_owner(inst, user_id=8, tenant_id="ten_a")
    assert not assert_instance_owner(inst, user_id=7, tenant_id="ten_b")
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
