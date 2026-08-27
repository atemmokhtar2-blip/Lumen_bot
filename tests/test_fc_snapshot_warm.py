"""Snapshot / warm-pool contract tests (no live KVM required)."""
from __future__ import annotations

from pathlib import Path

import pytest


def test_snapshot_artifacts_paths(tmp_path, monkeypatch):
    monkeypatch.setenv("TBE_FC_SNAPSHOT_DIR", str(tmp_path))
    from lumen.engine.services.sandbox_runtime.fc_snapshot import artifacts_for
    a = artifacts_for("base")
    assert a.snapshot_path.parent == tmp_path / "base"
    assert a.mem_path.name == "vm.mem"
    assert a.exists() is False


def test_load_payload_requires_files(tmp_path, monkeypatch):
    monkeypatch.setenv("TBE_FC_SNAPSHOT_DIR", str(tmp_path))
    from lumen.engine.services.sandbox_runtime.fc_snapshot import (
        artifacts_for,
        load_snapshot_payload,
    )
    a = artifacts_for("base")
    with pytest.raises(RuntimeError, match="snapshot_missing"):
        load_snapshot_payload(a)


def test_load_payload_ok(tmp_path, monkeypatch):
    monkeypatch.setenv("TBE_FC_SNAPSHOT_DIR", str(tmp_path))
    from lumen.engine.services.sandbox_runtime.fc_snapshot import (
        artifacts_for,
        load_snapshot_payload,
    )
    a = artifacts_for("base")
    a.snapshot_path.write_bytes(b"snap")
    a.mem_path.write_bytes(b"mem")
    body = load_snapshot_payload(a, resume=True)
    assert body["resume_vm"] is True
    assert body["mem_backend"]["backend_type"] == "File"
    assert "snapshot_path" in body


def test_warm_pool_register(tmp_path, monkeypatch):
    monkeypatch.setenv("TBE_FC_SNAPSHOT_DIR", str(tmp_path))
    from lumen.engine.services.sandbox_runtime.fc_snapshot import (
        artifacts_for,
        get_warm_pool,
    )
    a = artifacts_for("base")
    a.snapshot_path.write_bytes(b"s")
    a.mem_path.write_bytes(b"m")
    pool = get_warm_pool()
    pool.register("base", a)
    assert pool.available("base")


def test_warm_start_disabled_returns_none(monkeypatch, tmp_path):
    monkeypatch.delenv("TBE_FC_WARM_POOL", raising=False)
    from lumen.engine.services.sandbox_runtime.fc_warm_start import try_warm_start
    assert try_warm_start(
        firecracker_bin="/usr/bin/false",
        sock=tmp_path / "x.sock",
        log_path=tmp_path / "x.log",
    ) is None


def test_backend_source_has_warm_and_vsock():
    src = Path("lumen/engine/services/sandbox_runtime/firecracker_backend.py").read_text()
    assert "try_warm_start" in src
    assert "/vsock" in src
    assert "TBE_FC_VSOCK" in src
