"""Hosting must use sandbox_runtime only — no LocalProcess fallback."""
from __future__ import annotations

from pathlib import Path


def test_hosting_service_source_has_no_legacy_fallback():
    src = Path("lumen/engine/services/hosting/service.py").read_text(encoding="utf-8")
    assert "select_process_driver" not in src
    assert "LocalProcessDriver" not in src
    assert "start_sandboxed_bot" in src
    assert "sandbox_backend" in src


def test_worker_source_no_premature_harden():
    src = Path("lumen/engine/services/hosting/worker.py").read_text(encoding="utf-8")
    # harden_network must not be called before start_sandboxed_bot in worker
    assert "start_sandboxed_bot" in src
    # After our fix, worker should not import harden_network
    assert "from lumen.engine.services.sandbox_runtime.egress import harden_network" not in src


def test_select_skips_docker_harden_for_firecracker_source():
    src = Path("lumen/engine/services/sandbox_runtime/select.py").read_text(encoding="utf-8")
    assert 'backend.name != "firecracker"' in src
