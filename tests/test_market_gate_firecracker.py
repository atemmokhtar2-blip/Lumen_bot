"""Market gate accepts Firecracker commercial track."""
from __future__ import annotations

from pathlib import Path

import pytest


def test_market_gate_firecracker_track(monkeypatch, tmp_path):
    monkeypatch.setenv("TBE_MARKET_GATE", "1")
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("TBE_SANDBOX_BACKEND", "firecracker")
    monkeypatch.setenv("TBE_TOKEN_SECRET", "x" * 40)
    monkeypatch.setenv("TBE_SCALE_MODE", "1")
    monkeypatch.setenv("TBE_DATABASE_URL", "postgresql://u:p@localhost/db")
    monkeypatch.setenv("TBE_ALLOW_LOCAL_PROCESS", "0")
    k = tmp_path / "vmlinux"
    r = tmp_path / "rootfs.ext4"
    k.write_text("k")
    r.write_text("r")
    monkeypatch.setenv("TBE_FC_KERNEL", str(k))
    monkeypatch.setenv("TBE_FC_ROOTFS", str(r))
    monkeypatch.setenv("TBE_FIRECRACKER_BIN", "/usr/bin/firecracker")
    monkeypatch.setenv("TBE_JAILER_BIN", "/usr/bin/jailer")
    monkeypatch.setenv("TBE_FC_TAP", "tap0")
    monkeypatch.setenv("TBE_FC_TOKEN_IN_BOOTARGS", "0")
    monkeypatch.setenv("TBE_FC_REQUIRE_JAILER", "1")
    from lumen.engine.services.hosting.market_gate import evaluate_market_gate
    g = evaluate_market_gate()
    assert g.ok, g.missing
    assert g.track == "firecracker"


def test_market_gate_rejects_incomplete_fc(monkeypatch):
    monkeypatch.setenv("TBE_MARKET_GATE", "1")
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("TBE_SANDBOX_BACKEND", "firecracker")
    monkeypatch.setenv("TBE_TOKEN_SECRET", "x" * 40)
    monkeypatch.setenv("TBE_SCALE_MODE", "1")
    monkeypatch.setenv("TBE_DATABASE_URL", "postgresql://u:p@localhost/db")
    monkeypatch.delenv("TBE_FC_KERNEL", raising=False)
    monkeypatch.delenv("TBE_FC_ROOTFS", raising=False)
    from lumen.engine.services.hosting.market_gate import evaluate_market_gate
    g = evaluate_market_gate()
    assert g.ok is False
    assert any("KERNEL" in m or "ROOTFS" in m or "firecracker" in m.lower() for m in g.missing)
