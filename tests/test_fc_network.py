"""Per-VM Firecracker network isolation unit tests."""
from __future__ import annotations

import pytest


def test_allocate_plan_unique_taps():
    from lumen.engine.services.sandbox_runtime.fc_network import allocate_plan
    a = allocate_plan("fc-1-aaaaaaaaaa", "AA:FC:00:00:00:01")
    b = allocate_plan("fc-2-bbbbbbbbbb", "AA:FC:00:00:00:02")
    assert a.tap_name != b.tap_name
    assert a.netns != b.netns
    assert len(a.tap_name) <= 15


def test_shared_static_tap_forbidden(monkeypatch):
    monkeypatch.setenv("TBE_FC_AUTO_NET", "1")
    monkeypatch.setenv("TBE_FC_TAP", "tap0")
    monkeypatch.delenv("TBE_FC_ALLOW_SHARED_TAP", raising=False)
    from lumen.engine.services.sandbox_runtime.fc_network import resolve_start_network
    with pytest.raises(RuntimeError, match="shared_TBE_FC_TAP_forbidden"):
        resolve_start_network("fc-1-abc", "AA:FC:00:00:00:01")


def test_allow_no_net(monkeypatch):
    monkeypatch.setenv("TBE_FC_AUTO_NET", "0")
    monkeypatch.delenv("TBE_FC_TAP", raising=False)
    monkeypatch.delenv("TBE_FC_NETNS", raising=False)
    monkeypatch.setenv("TBE_FC_ALLOW_NO_NET", "1")
    from lumen.engine.services.sandbox_runtime.fc_network import resolve_start_network
    tap, ns, plan = resolve_start_network("fc-1-abc", "AA:FC:00:00:00:01")
    assert tap == ""
    assert plan is None
