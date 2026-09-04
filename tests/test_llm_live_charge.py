"""Live LLM credit charging — model-aware cost control tests."""
from __future__ import annotations

import pytest

from lumen.platform.credits import (
    InsufficientCreditsError,
    bind_charge_context,
    charge_bound_usage,
    charge_llm_step,
    clear_charge_context,
    credits_for_llm_usage,
    reset_credit_service_for_tests,
    tenant_id_from_user,
)
from lumen.platform.credits.memory_store import MemoryCreditsStore
from lumen.platform.credits.service import CreditService
from lumen.engine.services.evaluation.cost_model import estimate_cost_usd, resolve_rates


@pytest.fixture
def credits_simple(monkeypatch):
    reset_credit_service_for_tests()
    store = MemoryCreditsStore()
    svc = CreditService(store)
    monkeypatch.setenv("LUMEN_LIVE_LLM_CHARGE", "1")
    monkeypatch.setenv("LUMEN_LLM_FLAT_1K_PRICING", "0")
    monkeypatch.setenv("LUMEN_CREDITS_PER_USD", "1000")
    monkeypatch.setenv("DATABASE_URL", "")
    monkeypatch.setenv("POSTGRES_URL", "")
    monkeypatch.setenv("POSTGRESQL_URL", "")
    import lumen.platform.credits.service as svc_mod

    svc_mod._SVC = svc
    monkeypatch.setattr(svc_mod, "get_credit_service", lambda: svc)
    import lumen.platform.credits as pkg

    monkeypatch.setattr(pkg, "get_credit_service", lambda: svc)
    return svc


def test_tenant_id_from_user():
    assert tenant_id_from_user(42) == "tg:42"
    assert tenant_id_from_user(0) == ""


def test_model_aware_rates_differ():
    g = resolve_rates("groq", "llama-3.3")
    a = resolve_rates("anthropic", "claude-3-5-sonnet")
    assert g[0] < a[0] and g[1] < a[1]


def test_same_tokens_expensive_model_costs_more():
    base = {"prompt_tokens": 50_000, "completion_tokens": 20_000}
    cheap = credits_for_llm_usage({**base, "provider": "groq", "model_id": "llama-3.3"})
    mid = credits_for_llm_usage({**base, "provider": "openai", "model_id": "gpt-4o-mini"})
    exp = credits_for_llm_usage({**base, "provider": "anthropic", "model_id": "claude-3-5-sonnet"})
    assert cheap < mid < exp
    assert cheap >= 1


def test_credits_for_usage_zero_empty():
    assert credits_for_llm_usage({}) == 0
    assert credits_for_llm_usage(None) == 0


def test_estimate_cost_uses_provider():
    u = {"prompt_tokens": 1_000_000, "completion_tokens": 0, "provider": "groq", "model_id": "llama"}
    # 1M prompt @ 0.05 = $0.05
    assert abs(estimate_cost_usd(u) - 0.05) < 1e-6


def test_charge_llm_step_success(credits_simple):
    credits_simple.credit_credits("tg:7", 1000, idempotency_key="fund-tg7-001")
    # small usage → few credits
    receipt = charge_llm_step(
        "tg:7",
        {"prompt_tokens": 10_000, "completion_tokens": 0, "provider": "openai", "model_id": "gpt-4o-mini"},
        state_id="run-1",
        step=1,
        call_index=1,
        credit_service=credits_simple,
    )
    assert receipt["charged"] is True
    assert receipt["credits"] >= 1
    assert credits_simple.get_wallet("tg:7").current_balance == 1000 - receipt["credits"]


def test_charge_llm_step_idempotent(credits_simple):
    credits_simple.credit_credits("tg:8", 500, idempotency_key="fund-tg8-001")
    u = {"prompt_tokens": 5000, "completion_tokens": 0, "provider": "openai", "model_id": "gpt-4o-mini"}
    r1 = charge_llm_step("tg:8", u, state_id="s", step=2, call_index=1, credit_service=credits_simple)
    r2 = charge_llm_step("tg:8", u, state_id="s", step=2, call_index=1, credit_service=credits_simple)
    assert r1["charged"] and r2["charged"]
    assert credits_simple.get_wallet("tg:8").current_balance == 500 - r1["credits"]


def test_charge_llm_step_insufficient_raises(credits_simple):
    credits_simple.credit_credits("tg:9", 1, idempotency_key="fund-tg9-001")
    with pytest.raises(InsufficientCreditsError):
        charge_llm_step(
            "tg:9",
            {
                "prompt_tokens": 500_000,
                "completion_tokens": 200_000,
                "provider": "anthropic",
                "model_id": "claude-3-5-sonnet",
            },
            state_id="s",
            step=3,
            call_index=1,
            credit_service=credits_simple,
        )


def test_charge_skipped_when_disabled(credits_simple, monkeypatch):
    monkeypatch.setenv("LUMEN_LIVE_LLM_CHARGE", "0")
    credits_simple.credit_credits("tg:10", 10, idempotency_key="fund-tg10-001")
    r = charge_llm_step(
        "tg:10",
        {"prompt_tokens": 2000, "completion_tokens": 2000, "provider": "openai", "model_id": "gpt-4o-mini"},
        state_id="s",
        step=1,
        call_index=1,
        credit_service=credits_simple,
    )
    assert r["skipped"] is True
    assert credits_simple.get_wallet("tg:10").current_balance == 10


def test_charge_skipped_anonymous(credits_simple):
    r = charge_llm_step(
        "",
        {"prompt_tokens": 1000, "completion_tokens": 100, "provider": "openai"},
        state_id="s",
        step=1,
        call_index=1,
        credit_service=credits_simple,
    )
    assert r["skipped"] is True


def test_bound_context_charges_and_raises(credits_simple):
    # Fund just enough for one small openai step
    credits_simple.credit_credits("tg:55", 5, idempotency_key="fund-tg55-001")
    tok = bind_charge_context(tenant_id="tg:55", state_id="run-x", step=1, call_index=0)
    try:
        u = {"prompt_tokens": 10_000, "completion_tokens": 0, "provider": "openai", "model_id": "gpt-4o-mini"}
        r = charge_bound_usage(u, provider="openai", model_id="gpt-4o-mini", credit_service=credits_simple)
        assert r and r["charged"]
        bal = credits_simple.get_wallet("tg:55").current_balance
        assert bal < 5
        # Huge anthropic call should fail
        with pytest.raises(InsufficientCreditsError):
            charge_bound_usage(
                {
                    "prompt_tokens": 200_000,
                    "completion_tokens": 100_000,
                    "provider": "anthropic",
                    "model_id": "claude-3-5-sonnet",
                },
                provider="anthropic",
                model_id="claude-3-5-sonnet",
                credit_service=credits_simple,
            )
    finally:
        clear_charge_context(tok)


def test_record_usage_charges_at_source(credits_simple):
    from lumen.engine.services.cline_runtime import agent_brain

    credits_simple.credit_credits("tg:101", 50, idempotency_key="fund-tg101-001")
    tok = bind_charge_context(tenant_id="tg:101", state_id="src", step=1, call_index=0)
    try:
        agent_brain._record_usage(
            "openai",
            "gpt-4o-mini",
            {"usage": {"prompt_tokens": 10_000, "completion_tokens": 0, "total_tokens": 10_000}},
        )
        bal = credits_simple.get_wallet("tg:101").current_balance
        assert bal < 50
        with pytest.raises(InsufficientCreditsError):
            agent_brain._record_usage(
                "anthropic",
                "claude-3-5-sonnet",
                {
                    "usage": {
                        "prompt_tokens": 500_000,
                        "completion_tokens": 200_000,
                        "total_tokens": 700_000,
                    }
                },
            )
    finally:
        clear_charge_context(tok)


def test_is_generation_allowed(credits_simple):
    from lumen.platform.balance_lifecycle import BalanceLifecycle, MemoryLifecycleStore

    lc = BalanceLifecycle(MemoryLifecycleStore(), credits_simple)
    credits_simple.credit_credits("tg:88", 10, idempotency_key="fund-tg88-001")
    ok, reason = lc.is_generation_allowed("tg:88")
    assert ok and reason == "ok"
    credits_simple.deduct_credits("tg:88", 10, idempotency_key="drain-tg88-001")
    ok2, reason2 = lc.is_generation_allowed("tg:88")
    assert not ok2


def test_user_facing_insufficient_message(monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "test")
    import importlib.util
    from pathlib import Path as P

    path = P("lumen/bot/sanitize.py")
    spec = importlib.util.spec_from_file_location("lumen_bot_sanitize_test", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    msg = mod.user_facing_generation_error(code="insufficient_credits:needed=5")
    assert "insufficient_credits" in msg
    assert "رصيد" in msg


def test_agent_loop_stops_when_balance_runs_out(credits_simple, monkeypatch):
    """Balance covers ~1 step of openai traffic → stops on next charge."""
    from lumen.engine.services.cline_runtime import agent_loop

    # ~1-2 credits for 10k prompt openai mini
    credits_simple.credit_credits("tg:99", 2, idempotency_key="fund-tg99-001")
    monkeypatch.setenv("CLINE_AGENT_MAX_STEPS", "5")
    monkeypatch.setenv("CLINE_LLM_RETRIES", "1")
    monkeypatch.setenv("CLINE_DECISION_CACHE", "0")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setenv("CLINE_ROUTER", "local")

    call_count = {"n": 0}

    def fake_decide(messages, **kwargs):
        call_count["n"] += 1
        from lumen.platform.credits.llm_live import charge_bound_usage

        usage = {
            "prompt_tokens": 10_000,
            "completion_tokens": 0,
            "provider": "openai",
            "model_id": "gpt-4o-mini",
        }
        receipt = charge_bound_usage(
            usage, provider="openai", model_id="gpt-4o-mini", credit_service=credits_simple
        )
        return {
            "thought": "step",
            "tool": "list_dir",
            "args": {"path": "."},
            "parse_ok": True,
            "provider": "openai",
            "model_id": "gpt-4o-mini",
            "usage": usage,
            "cache_hit": False,
            "credit_charge": receipt,
            "finish": False,
        }

    monkeypatch.setattr(agent_loop, "decide", fake_decide)
    monkeypatch.setattr(
        "lumen.engine.services.cline_runtime.agent_loop.select_model",
        lambda task="build": type("C", (), {"provider": "openai", "model_id": "gpt-4o-mini"})(),
    )
    monkeypatch.setattr(
        "lumen.engine.services.cline_runtime.agent_loop.select_model_for_goal",
        lambda **kw: (type("C", (), {"provider": "openai", "model_id": "gpt-4o-mini"})(), {}),
    )
    monkeypatch.setattr(
        "lumen.engine.services.cline_runtime.agent_loop.run_tool",
        lambda work_dir, tool, args: {"ok": True, "output": "[]"},
    )
    monkeypatch.setattr(
        "lumen.engine.services.cline_runtime.agent_loop.describe_runtime",
        lambda: {"provider": "openai", "model_id": "gpt-4o-mini"},
    )

    import tempfile

    with tempfile.TemporaryDirectory() as td:
        state = agent_loop.run_agent(
            work_dir=td,
            goal="list files only",
            ir_dict={"user_id": 99},
            max_steps=5,
        )

    assert state.stop_reason == "insufficient_credits"
    assert state.ok is False
    assert call_count["n"] <= 3


def test_provider_agent_does_not_override_insufficient(credits_simple, monkeypatch, tmp_path):
    """Acceptance must NOT promote insufficient_credits to ok=True."""
    from lumen.engine.services.cline_runtime.agent_state import AgentState
    from lumen.engine.services.cline_runtime import provider_agent

    def fake_run_agent(**kwargs):
        st = AgentState(work_dir=str(tmp_path), goal="x")
        st.ok = False
        st.stop_reason = "insufficient_credits"
        st.errors = ["insufficient_credits:needed=10:available=0:step=2"]
        st.files_written = ["main.py"]  # files exist — old bug promoted this to ok
        (tmp_path / "main.py").write_text("print(1)\n", encoding="utf-8")
        return st

    monkeypatch.setattr(provider_agent, "run_agent", fake_run_agent)
    monkeypatch.setattr(
        "lumen.engine.services.cline_runtime.agent_acceptance.check_agent_project",
        lambda *a, **k: {"ok": True, "missing": []},
    )

    raw = provider_agent.build({"user_id": 1, "request": "bot"}, str(tmp_path))
    assert raw["ok"] is False
    assert raw["metadata"].get("stop_reason") == "insufficient_credits"
    assert any("insufficient_credits" in str(e) for e in raw["errors"])


def test_engine_turn_binds_charge_context(credits_simple, monkeypatch):
    """engine_turn LLM path must bind charge context (no free LLM)."""
    from lumen.engine.services.multi_agent import engine_turn
    from lumen.platform.credits.llm_live import get_charge_context

    seen = {"bound": False}

    def fake_decide(messages, **kwargs):
        ctx = get_charge_context()
        seen["bound"] = bool(ctx and ctx.get("tenant_id") == "tg:42")
        return {
            "parse_ok": True,
            "tool": "",
            "reply": "مرحبا",
            "thought": "",
            "provider": "openai",
            "model_id": "gpt-4o-mini",
            "raw": '{"tool":"","reply":"مرحبا"}',
            "usage": {},
        }

    monkeypatch.setattr(
        "lumen.engine.services.cline_runtime.model_router.select_model",
        lambda task="plan": type(
            "C",
            (),
            {
                "provider": "openai",
                "model_id": "gpt-4o-mini",
                "key_present": lambda self=None: True,
            },
        )(),
    )
    monkeypatch.setattr(
        "lumen.engine.services.cline_runtime.agent_brain.decide",
        fake_decide,
    )
    out = engine_turn._agent_llm_decide("hello", user_id=42)
    assert seen["bound"] is True
    assert out.get("error") in ("", None) or out.get("reply")


def test_meter_http_response_model_aware(credits_simple):
    credits_simple.credit_credits("tg:77", 100, idempotency_key="fund-tg77-001")
    from lumen.platform.credits.llm_live import meter_http_response

    r = meter_http_response(
        {"usage": {"prompt_tokens": 10_000, "completion_tokens": 0, "total_tokens": 10_000}},
        provider="openai",
        model_id="gpt-4o-mini",
        tenant_id="tg:77",
        state_id="direct-test",
        credit_service=credits_simple,
    )
    assert r and r.get("charged") is True
    assert credits_simple.get_wallet("tg:77").current_balance < 100


def test_flush_pending_llm_charges(credits_simple, tmp_path, monkeypatch):
    monkeypatch.setenv("LUMEN_PENDING_LLM_DIR", str(tmp_path))
    credits_simple.credit_credits("tg:78", 50, idempotency_key="fund-tg78-001")
    from lumen.platform.credits.llm_live import enqueue_pending_llm_charge, flush_pending_llm_charges

    enqueue_pending_llm_charge(
        {
            "idempotency_key": "llm:tg:78:pending:1:1",
            "tenant_id": "tg:78",
            "state_id": "pending",
            "step": 1,
            "call_index": 1,
            "provider": "openai",
            "model_id": "gpt-4o-mini",
            "usage": {
                "prompt_tokens": 5000,
                "completion_tokens": 0,
                "provider": "openai",
                "model_id": "gpt-4o-mini",
            },
        }
    )
    stats = flush_pending_llm_charges(limit=10, credit_service=credits_simple)
    assert stats["seen"] >= 1
    assert stats["charged"] >= 1
