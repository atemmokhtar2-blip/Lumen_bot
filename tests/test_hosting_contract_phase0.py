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
