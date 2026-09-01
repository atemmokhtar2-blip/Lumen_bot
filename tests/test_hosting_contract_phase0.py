"""Phase 0 — Hosting contract locked to actual code.

These tests do not start sandboxes. They prove the frozen contract still
matches HostInstance, market_gate, isolation_policy, and plane separation.
"""
from __future__ import annotations

import ast
import inspect
from dataclasses import fields
from pathlib import Path

import pytest

from lumen.engine.services.hosting import contract as host_contract
from lumen.engine.services.hosting.service import HostInstance, HostResult, HostingService


REPO_ROOT = Path(__file__).resolve().parents[1]


def test_host_instance_fields_match_contract() -> None:
    actual = tuple(f.name for f in fields(HostInstance))
    host_contract.assert_host_instance_fields_match(actual)
    assert actual == host_contract.HOST_INSTANCE_FIELDS


def test_host_result_fields_match_contract() -> None:
    actual = tuple(f.name for f in fields(HostResult))
    assert actual == host_contract.HOST_RESULT_FIELDS


def test_hosting_lifecycle_methods_exist() -> None:
    for name in host_contract.HOSTING_LIFECYCLE_METHODS:
        assert hasattr(HostingService, name), f"HostingService missing {name}"
        assert callable(getattr(HostingService, name))


def test_permanent_host_plane_documented_on_service() -> None:
    doc = inspect.getdoc(inspect.getmodule(HostingService)) or ""
    doc_l = doc.lower()
    assert "permanent_host" in doc_l or "permanent host" in doc_l or "long-running" in doc_l
    assert "live" in doc_l or "trial" in doc_l
    # Must not claim LiveRunner is the permanent path
    assert "not the chat trial path" in doc_l or "trial is liverunner" in doc_l.replace(" ", "")


def test_plane_modules_are_importable() -> None:
    import importlib

    for plane, mod_name in host_contract.PLANE_MODULES.items():
        mod = importlib.import_module(mod_name)
        assert mod is not None, plane


def test_production_backend_is_firecracker_only() -> None:
    assert host_contract.PRODUCTION_BACKEND == "firecracker"
    assert "firecracker" not in host_contract.DEV_ONLY_BACKENDS
    assert host_contract.DEV_ONLY_BACKENDS == frozenset({"gvisor", "dind", "docker"})


def test_market_gate_rejects_dev_backends_in_source() -> None:
    src = (REPO_ROOT / "lumen/engine/services/hosting/market_gate.py").read_text(encoding="utf-8")
    assert "gvisor" in src and "dind" in src and "docker" in src
    assert "Firecracker" in src or "firecracker" in src
    assert "TBE_TOKEN_SECRET" in src
    assert "TBE_SCALE_MODE" in src
    assert "TBE_ALLOW_LOCAL_PROCESS" in src
    # Commercial track refuses weak backends
    assert 'pref in {"gvisor", "dind", "docker"}' in src or "gvisor" in src


def test_isolation_policy_fail_closed_in_source() -> None:
    src = (REPO_ROOT / "lumen/engine/services/isolation_policy.py").read_text(encoding="utf-8")
    assert "require_strong_isolation" in src
    assert "Firecracker" in src or "firecracker" in src
    assert "LocalProcess" in src or "allow_local" in src
    assert "is_multi_tenant" in src
    assert "strong_sandbox_available" in src


def test_select_production_path_firecracker_only() -> None:
    src = (REPO_ROOT / "lumen/engine/services/sandbox_runtime/select.py").read_text(
        encoding="utf-8"
    )
    assert "is_production_sandbox_path" in src
    assert "_PRIMARY" in src or "firecracker" in src
    assert "gvisor" in src  # listed as dev-only, not primary


def test_token_fingerprint_algorithm() -> None:
    import hashlib

    raw = "123456:ABC-DEF"
    expected = hashlib.sha256(raw.encode()).hexdigest()[:16]
    assert host_contract.token_fingerprint(raw) == expected
    assert host_contract.token_fingerprint("") == ""
    assert host_contract.token_fingerprint("  ") == ""


def test_sqlite_state_store_forbidden_outside_dev_in_source() -> None:
    src = (REPO_ROOT / "lumen/engine/services/hosting/state_store.py").read_text(
        encoding="utf-8"
    )
    assert "forbidden outside ENVIRONMENT=dev" in src or "forbidden outside" in src
    assert "PgHostStateStore" in src or "postgresql" in src.lower()


def test_start_gate_order_non_empty_and_stable() -> None:
    assert len(host_contract.START_GATE_ORDER) >= 8
    assert host_contract.START_GATE_ORDER[0] == "project_path_exists"
    assert "market_gate" in host_contract.START_GATE_ORDER
    assert "user_sandbox_containment" in host_contract.START_GATE_ORDER


def test_security_invariants_mention_token_and_sandbox() -> None:
    joined = " ".join(host_contract.SECURITY_INVARIANTS)
    assert "token_fp" in joined
    assert "user_sandbox" in joined
    assert "firecracker" in joined


def test_phase0_gaps_explicit() -> None:
    gaps = host_contract.PHASE0_KNOWN_GAPS
    assert any("platform" in g for g in gaps)
    assert any("webhook" in g for g in gaps)


def test_host_instance_has_no_platform_field_yet() -> None:
    """Gap freeze: platform is not on HostInstance until Phase 2."""
    names = {f.name for f in fields(HostInstance)}
    assert "platform" not in names
    assert "webhook_public_url" not in names


def test_hosting_contract_doc_exists_and_references_planes() -> None:
    path = REPO_ROOT / "docs/HOSTING_CONTRACT.md"
    assert path.is_file(), "docs/HOSTING_CONTRACT.md missing"
    text = path.read_text(encoding="utf-8")
    assert "PERMANENT_HOST" in text
    assert "TRIAL_CHAT" in text
    assert "HostInstance" in text
    assert "market_gate" in text
    assert "Firecracker" in text or "firecracker" in text
    for field in host_contract.HOST_INSTANCE_FIELDS:
        assert field in text, f"docs missing field {field}"


def test_architecture_links_hosting_contract() -> None:
    text = (REPO_ROOT / "docs/ARCHITECTURE.md").read_text(encoding="utf-8")
    assert "HOSTING_CONTRACT.md" in text
    assert "PERMANENT_HOST" in text
    assert "TRIAL_CHAT" in text


def test_host_instance_ast_matches_contract_without_import_side_effects() -> None:
    """Second path: AST parse service.py so we don't rely only on import."""
    src = (REPO_ROOT / "lumen/engine/services/hosting/service.py").read_text(encoding="utf-8")
    tree = ast.parse(src)
    found = None
    for node in tree.body:
        if isinstance(node, ast.ClassDef) and node.name == "HostInstance":
            found = tuple(
                item.target.id
                for item in node.body
                if isinstance(item, ast.AnnAssign) and isinstance(item.target, ast.Name)
            )
            break
    assert found is not None
    assert found == host_contract.HOST_INSTANCE_FIELDS


def test_contract_module_exports_are_final_tuples() -> None:
    assert isinstance(host_contract.HOST_INSTANCE_FIELDS, tuple)
    assert isinstance(host_contract.START_GATE_ORDER, tuple)
    assert isinstance(host_contract.DEV_ONLY_BACKENDS, frozenset)


def test_pydantic_host_instance_record_validates_and_builds() -> None:
    from lumen.engine.schemas.hosting_contract import HostInstanceRecord

    rec = HostInstanceRecord.from_row(
        {
            "instance_id": "host-abc123",
            "user_id": 42,
            "project_path": "/tmp/user/project",
            "status": "running",
            "token_fp": "a" * 16,
            "last_diagnosis": "{}",
        }
    )
    inst = rec.to_host_instance()
    assert inst.instance_id == "host-abc123"
    assert inst.user_id == 42
    assert inst.status == "running"
    assert inst.last_diagnosis == {}


def test_pydantic_rejects_raw_token_in_token_fp() -> None:
    from pydantic import ValidationError
    from lumen.engine.schemas.hosting_contract import HostInstanceRecord

    with pytest.raises(ValidationError):
        HostInstanceRecord.from_row(
            {
                "instance_id": "host-x",
                "user_id": 1,
                "project_path": "/p",
                "status": "stopped",
                "token_fp": "123456789:AAHdqTcvCH1vGWJxfSeofSAs0K5PALDsaw",
            }
        )


def test_pydantic_rejects_missing_required() -> None:
    from pydantic import ValidationError
    from lumen.engine.schemas.hosting_contract import HostInstanceRecord

    with pytest.raises(ValidationError):
        HostInstanceRecord.from_row({"user_id": 1, "project_path": "/p"})


def test_service_inst_from_row_uses_pydantic_contract() -> None:
    src = (REPO_ROOT / "lumen/engine/services/hosting/service.py").read_text(encoding="utf-8")
    assert "HostInstanceRecord" in src
    assert "to_host_instance" in src


def test_service_uses_contract_token_fingerprint() -> None:
    src = (REPO_ROOT / "lumen/engine/services/hosting/service.py").read_text(encoding="utf-8")
    assert "token_fingerprint" in src
    assert "hexdigest()[:16]" not in src


def test_start_source_contains_gate_markers_in_order() -> None:
    src = (REPO_ROOT / "lumen/engine/services/hosting/service.py").read_text(encoding="utf-8")
    start_at = src.find("def start(")
    assert start_at > 0
    stop_at = src.find("\n    def stop(", start_at)
    body = src[start_at : stop_at if stop_at > 0 else start_at + 15000]
    markers = [
        "is_under_sandbox",
        "decide_isolation",
        "strong_sandbox_available",
        "evaluate_market_gate",
    ]
    positions = [body.find(m) for m in markers]
    assert all(p >= 0 for p in positions), positions
    assert positions == sorted(positions), list(zip(markers, positions))


def test_market_gate_evaluate_live_dev_skip(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ENVIRONMENT", "test")
    monkeypatch.setenv("TBE_MARKET_GATE", "0")
    from lumen.engine.services.hosting.market_gate import evaluate_market_gate

    gate = evaluate_market_gate()
    assert gate.ok is True


def test_market_gate_evaluate_live_production_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("TBE_MARKET_GATE", "1")
    monkeypatch.setenv("TBE_TOKEN_SECRET", "short")
    monkeypatch.setenv("TBE_SCALE_MODE", "1")
    monkeypatch.setenv("TBE_DATABASE_URL", "postgresql://u:p@localhost/db")
    monkeypatch.setenv("TBE_ALLOW_LOCAL_PROCESS", "0")
    monkeypatch.setenv("TBE_SANDBOX_BACKEND", "firecracker")
    monkeypatch.delenv("TBE_FC_KERNEL", raising=False)
    monkeypatch.delenv("TBE_FC_ROOTFS", raising=False)
    from lumen.engine.services.hosting.market_gate import evaluate_market_gate

    gate = evaluate_market_gate()
    assert gate.ok is False
    assert gate.missing


def test_isolation_decide_multi_tenant_requires_strong(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("TBE_MULTI_TENANT", "1")
    from lumen.engine.services.isolation_policy import decide_isolation

    d = decide_isolation()
    assert d.require_strong_isolation is True
    assert d.allow_local is False


def test_planes_pydantic_frozen() -> None:
    from lumen.engine.schemas.hosting_contract import PERMANENT_PLANE, TRIAL_PLANE

    assert PERMANENT_PLANE.long_running is True
    assert TRIAL_PLANE.long_running is False
    assert "hosting" in PERMANENT_PLANE.module
    assert "live_runner" in TRIAL_PLANE.module


def test_save_path_validates_through_pydantic() -> None:
    src = (REPO_ROOT / "lumen/engine/services/hosting/service.py").read_text(encoding="utf-8")
    assert "from_host_instance" in src
    assert "to_persist_dict" in src
    # _save_unlocked must not write raw asdict without validation
    save_at = src.find("def _save_unlocked")
    assert save_at > 0
    chunk = src[save_at : save_at + 400]
    assert "HostInstanceRecord" in chunk
    assert "asdict(inst)" not in chunk


def test_roundtrip_record_persist_dict() -> None:
    from lumen.engine.schemas.hosting_contract import HostInstanceRecord
    from lumen.engine.services.hosting.service import HostInstance

    inst = HostInstance(
        instance_id="host-rt1",
        user_id=7,
        project_path="/sandbox/u/p",
        status="running",
        token_fp="b" * 16,
    )
    rec = HostInstanceRecord.from_host_instance(inst)
    d = rec.to_persist_dict()
    back = HostInstanceRecord.from_row(d).to_host_instance()
    assert back.instance_id == inst.instance_id
    assert back.user_id == inst.user_id
    assert back.token_fp == inst.token_fp


def test_sqlite_upsert_persists_sandbox_backend(tmp_path, monkeypatch) -> None:
    """Regression: INSERT columns must include sandbox_backend (binding count bug)."""
    monkeypatch.setenv("ENVIRONMENT", "test")
    from lumen.engine.services.hosting.state_store import HostingStateStore
    from lumen.engine.schemas.hosting_contract import HostInstanceRecord

    db = tmp_path / "instances.sqlite3"
    store = HostingStateStore(db)
    rec = HostInstanceRecord.from_row(
        {
            "instance_id": "host-sbx1",
            "user_id": 9,
            "project_path": "/tmp/p",
            "status": "running",
            "sandbox_backend": "firecracker",
            "token_fp": "c" * 16,
        }
    )
    store.upsert(rec.to_persist_dict())
    row = store.get("host-sbx1")
    assert row is not None
    assert row.get("sandbox_backend") == "firecracker"
    assert row.get("token_fp") == "c" * 16
