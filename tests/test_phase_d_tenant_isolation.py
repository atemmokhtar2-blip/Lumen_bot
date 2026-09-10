"""Phase D — multi-tenant isolation wiring."""
from __future__ import annotations

import pytest


def test_redis_keys_namespaced():
    from lumen.platform.tenant_isolation import host_instance_redis_key, host_user_index_key
    assert "t:ten_abc" in host_instance_redis_key("host-1", tenant_id="ten_abc")
    assert host_instance_redis_key("host-1", tenant_id="") == "lumen:host:inst:host-1"
    assert "t:ten_x" in host_user_index_key(42, tenant_id="ten_x")


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
    assert "t_ten_a" in str(d1)
    assert "u_1" in str(d1)


def test_host_service_start_accepts_tenant_id():
    import inspect
    from lumen.engine.services.hosting.service import HostingService
    sig = inspect.signature(HostingService.start)
    assert "tenant_id" in sig.parameters


def test_hosts_api_passes_tenant_id():
    src = open("lumen/api/routes/hosts.py", encoding="utf-8").read()
    assert "tenant_id=tenant.tenant_id" in src


def test_host_instance_record_has_tenant():
    from lumen.engine.schemas.hosting_contract import HostInstanceRecord
    r = HostInstanceRecord(
        instance_id="host-1",
        user_id=1,
        tenant_id="ten_x",
        project_path="/tmp/p",
    )
    assert r.tenant_id == "ten_x"
    inst = r.to_host_instance()
    assert inst.tenant_id == "ten_x"
