"""Live LLM credit charging — root-cause cost control tests."""
from __future__ import annotations

import os

import pytest

from lumen.platform.credits import (
    InsufficientCreditsError,
    charge_llm_step,
    credits_for_llm_usage,
    get_credit_service,
    reset_credit_service_for_tests,
    tenant_id_from_user,
)
from lumen.platform.credits.memory_store import MemoryCreditsStore
from lumen.platform.credits.service import CreditService
from lumen.engine.services.cline_runtime.agent_state import AgentState


@pytest.fixture
def credits(monkeypatch):
    reset_credit_service_for_tests()
    store = MemoryCreditsStore()
    svc = CreditService(store)
    monkeypatch.setattr(
        "lumen.platform.credits.service.get_credit_service",
        lambda: svc,
    )
    monkeypatch.setattr(
        "lumen.platform.credits.get_credit_service",
        lambda: svc,
    )
    # Force live charge on
    monkeypatch.setenv("LUMEN_LIVE_LLM_CHARGE", "1")
    return svc


def test_tenant_id_from_user():
    assert tenant_id_from_user(42) == "tg:42"
    assert tenant_id_from_user(0) == ""
    assert tenant_id_from_user(None) == ""


def test_credits_for_usage_uses_1k_rules(credits):
    # 1500 prompt + 500 completion → 2 * 1 + 1 * 3 = 5
    n = credits_for_llm_usage(
        {"prompt_tokens": 1500, "completion_tokens": 500},
        credit_service=credits,
    )
    assert n == 5


def test_credits_for_usage_zero_empty():
    assert credits_for_llm_usage({}) == 0
    assert credits_for_llm_usage(None) == 0


def test_credits_for_usage_floor_one_token(credits):
    n = credits_for_llm_usage(
        {"prompt_tokens": 1, "completion_tokens": 0},
        credit_service=credits,
    )
    assert n >= 1


def test_charge_llm_step_success(credits):
    credits.credit_credits("tg:7", 100, idempotency_key="fund-tg7-001")
    receipt = charge_llm_step(
        "tg:7",
        {"prompt_tokens": 1000, "completion_tokens": 1000},
        state_id="run-1",
        step=1,
        call_index=1,
        credit_service=credits,
    )
    assert receipt["charged"] is True
    assert receipt["credits"] == 1 + 3  # 1k prompt + 1k completion
    w = credits.get_wallet("tg:7")
    assert w.current_balance == 100 - 4


def test_charge_llm_step_idempotent(credits):
    credits.credit_credits("tg:8", 50, idempotency_key="fund-tg8-001")
    u = {"prompt_tokens": 1000, "completion_tokens": 0}
    r1 = charge_llm_step("tg:8", u, state_id="s", step=2, call_index=1, credit_service=credits)
    r2 = charge_llm_step("tg:8", u, state_id="s", step=2, call_index=1, credit_service=credits)
    assert r1["charged"] and r2["charged"]
    # Second call replays same ledger entry — balance only dropped once
    w = credits.get_wallet("tg:8")
    assert w.current_balance == 50 - r1["credits"]


def test_charge_llm_step_insufficient_raises(credits):
    credits.credit_credits("tg:9", 1, idempotency_key="fund-tg9-001")
    with pytest.raises(InsufficientCreditsError) as ei:
        charge_llm_step(
            "tg:9",
            {"prompt_tokens": 5000, "completion_tokens": 5000},
            state_id="s",
            step=3,
            call_index=1,
            credit_service=credits,
        )
    assert ei.value.needed > 1
    assert ei.value.tenant_id == "tg:9"


def test_charge_skipped_when_disabled(credits, monkeypatch):
    monkeypatch.setenv("LUMEN_LIVE_LLM_CHARGE", "0")
    credits.credit_credits("tg:10", 10, idempotency_key="fund-tg10-001")
    r = charge_llm_step(
        "tg:10",
        {"prompt_tokens": 2000, "completion_tokens": 2000},
        state_id="s",
        step=1,
        call_index=1,
        credit_service=credits,
    )
    assert r["skipped"] is True
    assert credits.get_wallet("tg:10").current_balance == 10


def test_charge_skipped_anonymous(credits):
    r = charge_llm_step(
        "",
        {"prompt_tokens": 1000, "completion_tokens": 100},
        state_id="s",
        step=1,
        call_index=1,
        credit_service=credits,
    )
    assert r["skipped"] is True
    assert r["reason"] == "no_tenant"


def test_agent_loop_stops_on_insufficient_credits(credits, monkeypatch):
    """Agent loop with balance for ~1 step must stop with insufficient_credits."""
    from lumen.engine.services.cline_runtime import agent_loop

    # Fund only 2 credits — one small step (1k+0 → 1 credit) then second should fail
    credits.credit_credits("tg:99", 2, idempotency_key="fund-tg99-001")
    monkeypatch.setenv("CLINE_AGENT_MAX_STEPS", "5")
    monkeypatch.setenv("CLINE_LLM_RETRIES", "1")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-live-charge")
    monkeypatch.setenv("CLINE_ROUTER", "local")

    call_count = {"n": 0}

    def fake_decide(messages, **kwargs):
        call_count["n"] += 1
        # Each decide reports 1500 prompt tokens → ceil(1.5)=2 * 1 = 2 credits for first
        # second call needs another 2 → insufficient
        return {
            "thought": "step",
            "tool": "list_dir",
            "args": {"path": "."},
            "params": {},
            "finish": False,
            "summary": "",
            "reply": "",
            "raw": "",
            "parse_ok": True,
            "provider": "openai",
            "model_id": "gpt-test",
            "usage": {"prompt_tokens": 1500, "completion_tokens": 0, "provider": "openai", "model_id": "gpt-test"},
            "cache_hit": False,
        }

    monkeypatch.setattr(agent_loop, "decide", fake_decide)
    monkeypatch.setattr(
        "lumen.engine.services.cline_runtime.agent_loop.select_model",
        lambda task="build": type("C", (), {"provider": "openai", "model_id": "gpt-test"})(),
    )
    monkeypatch.setattr(
        "lumen.engine.services.cline_runtime.agent_loop.select_model_for_goal",
        lambda **kw: (
            type("C", (), {"provider": "openai", "model_id": "gpt-test"})(),
            {},
        ),
    )
    monkeypatch.setattr(
        "lumen.engine.services.cline_runtime.agent_loop.run_tool",
        lambda work_dir, tool, args: {"ok": True, "output": "[]"},
    )
    # Describe runtime no-op path
    monkeypatch.setattr(
        "lumen.engine.services.cline_runtime.agent_loop.describe_runtime",
        lambda: {"provider": "openai", "model_id": "gpt-test"},
    )

    import tempfile
    from pathlib import Path

    with tempfile.TemporaryDirectory() as td:
        state = agent_loop.run_agent(
            work_dir=td,
            goal="list files only",
            ir_dict={"user_id": 99},
            max_steps=5,
        )

    assert state.stop_reason == "insufficient_credits"
    assert state.ok is False
    assert any("insufficient_credits" in e for e in (state.errors or []))
    # First step charged 2 credits → balance 0
    assert credits.get_wallet("tg:99").current_balance == 0
    # Should not have run many steps
    assert call_count["n"] <= 2
