"""Temporal routing must not bypass the active Telegram HITL path."""
from __future__ import annotations


def test_temporal_requires_explicit_opt_in_and_hitl_disabled(monkeypatch):
    from lumen.engine.services.multi_agent import temporal_client_run as temporal

    monkeypatch.setattr(temporal, "temporal_configured", lambda: True)
    monkeypatch.setenv("LUMEN_GENERATE_VIA_TEMPORAL", "1")
    monkeypatch.delenv("MULTI_AGENT_LANGGRAPH_HITL", raising=False)
    assert temporal.temporal_generation_enabled() is False

    monkeypatch.setenv("MULTI_AGENT_LANGGRAPH_HITL", "1")
    assert temporal.temporal_generation_enabled() is False

    monkeypatch.setenv("MULTI_AGENT_LANGGRAPH_HITL", "0")
    assert temporal.temporal_generation_enabled() is True

    monkeypatch.setenv("LUMEN_GENERATE_VIA_TEMPORAL", "0")
    assert temporal.temporal_generation_enabled() is False
