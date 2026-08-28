"""Batch 6 emit helper + host failure classification."""
from __future__ import annotations

from lumen.bot.ui.emit_context import classify_host_failure
from lumen.engine.services.ui_state import UiEventKind, apply_event, EngineUiState, buttons_for_state


def test_classify_host_failure():
    assert classify_host_failure("الاستضافة تتطلب عزل Firecracker") == "sandbox_unavailable"
    assert classify_host_failure("مسار المشروع غير موجود") == "no_project"
    assert classify_host_failure("وصلت للحد") == "host_limit"
    assert classify_host_failure("unknown boom") == "host_failed"


def test_event_roundtrip_buttons():
    st = apply_event(EngineUiState(), UiEventKind.HOST_FAILED, detail="x")
    actions = [b.action for row in buttons_for_state(st) for b in row]
    assert "open_dashboard" in actions
