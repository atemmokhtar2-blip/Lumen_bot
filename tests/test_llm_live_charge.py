"""Live LLM credit charging — root-cause cost control tests."""
from __future__ import annotations

import pytest

from lumen.platform.credits import (
    InsufficientCreditsError,
    bind_charge_context,
    charge_bound_usage,
    charge_llm_step,
    clear_charge_context,
    credits_for_llm_usage,
    get_credit_service,
    reset_credit_service_for_tests,
    tenant_id_from_user,
)
from lumen.platform.credits.memory_store import MemoryCreditsStore
from lumen.platform.credits.service import CreditService


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
    monkeypatch.setattr(
        "lumen.platform.credits.llm_live.get_credit_service",
        lambda: svc,
        raising=False,
    )
    # Patch inside charge_llm_step import path
    import lumen.platform.credits.llm_live as llm_live

    monkeypatch.setattr(
        llm_live,
        "charge_llm_step",
        lambda *a, **k: _charge_with(svc, *a, **k) if False else __import__(
            "lumen.platform.credits.llm_live", fromlist=["charge_llm_step"]
        ),
    )
    # Simpler: monkeypatch get_credit_service where llm_live imports it
    def _get():
        return svc

    monkeypatch.setattr(
        "lumen.platform.credits.llm_live.charge_llm_step",
        lambda tenant_id, usage, **kw: _real_charge(svc, tenant_id, usage, **kw),
    )

    monkeypatch.setenv("LUMEN_LIVE_LLM_CHARGE", "1")
    return svc


def _real_charge(svc, tenant_id, usage, **kw):
    from lumen.platform.credits import llm_live as mod
    # call original logic with injected service
    kw = dict(kw)
    kw["credit_service"] = svc
    # Use unbound original by reconstructing
    amount = mod.credits_for_llm_usage(usage, credit_service=svc)
    # inline minimal path using public API with service
    from lumen.platform.credits.llm_live import live_charge_enabled

    if not live_charge_enabled():
        return {"charged": False, "skipped": True, "reason": "live_charge_disabled", "credits": 0}
    tid = str(tenant_id or "").strip()
    if not tid:
        return {"charged": False, "skipped": True, "reason": "no_tenant", "credits": 0}
    if amount <= 0:
        return {"charged": False, "skipped": True, "reason": "zero_usage", "credits": 0}
    sid = str(kw.get("state_id") or "nostate")
    step = int(kw.get("step") or 0)
    call_index = int(kw.get("call_index") or 0)
    idem = f"llm:{tid}:{sid}:{step}:{call_index}"
    if len(idem) > 180:
        idem = idem[:180]
    result = svc.deduct_credits(
        tid,
        amount,
        reason="llm_step",
        reference_id=sid,
        idempotency_key=idem,
        metadata={},
    )
    if not result.ok:
        available = 0
        try:
            available = int(svc.get_wallet(tid).available)
        except Exception:
            pass
        raise InsufficientCreditsError(
            tid, needed=amount, available=available, reason=str(result.reason), step=step
        )
    try:
        from lumen.platform.balance_lifecycle import get_balance_lifecycle
        get_balance_lifecycle().on_balance_changed(tid)
    except Exception:
        pass
    return {"charged": True, "credits": amount, "skipped": False, "reason": "ok", "tenant_id": tid, "step": step}


@pytest.fixture
def credits_simple(monkeypatch):
    reset_credit_service_for_tests()
    store = MemoryCreditsStore()
    svc = CreditService(store)
    monkeypatch.setenv("LUMEN_LIVE_LLM_CHARGE", "1")
    monkeypatch.setenv("DATABASE_URL", "")
    monkeypatch.setenv("POSTGRES_URL", "")
    monkeypatch.setenv("POSTGRESQL_URL", "")
    # Force memory service globally
    import lumen.platform.credits.service as svc_mod

    svc_mod._SVC = svc
    monkeypatch.setattr(svc_mod, "get_credit_service", lambda: svc)
    import lumen.platform.credits as pkg

    monkeypatch.setattr(pkg, "get_credit_service", lambda: svc)
    return svc


def test_tenant_id_from_user():
    assert tenant_id_from_user(42) == "tg:42"
    assert tenant_id_from_user(0) == ""
    assert tenant_id_from_user(None) == ""


def test_credits_for_usage_uses_1k_rules(credits_simple):
    n = credits_for_llm_usage(
        {"prompt_tokens": 1500, "completion_tokens": 500},
        credit_service=credits_simple,
    )
    assert n == 5


def test_credits_for_usage_zero_empty():
    assert credits_for_llm_usage({}) == 0
    assert credits_for_llm_usage(None) == 0


def test_credits_for_usage_floor_one_token(credits_simple):
    n = credits_for_llm_usage(
        {"prompt_tokens": 1, "completion_tokens": 0},
        credit_service=credits_simple,
    )
    assert n >= 1


def test_charge_llm_step_success(credits_simple):
    credits_simple.credit_credits("tg:7", 100, idempotency_key="fund-tg7-001")
    receipt = charge_llm_step(
        "tg:7",
        {"prompt_tokens": 1000, "completion_tokens": 1000},
        state_id="run-1",
        step=1,
        call_index=1,
        credit_service=credits_simple,
    )
    assert receipt["charged"] is True
    assert receipt["credits"] == 4
    assert credits_simple.get_wallet("tg:7").current_balance == 96


def test_charge_llm_step_idempotent(credits_simple):
    credits_simple.credit_credits("tg:8", 50, idempotency_key="fund-tg8-001")
    u = {"prompt_tokens": 1000, "completion_tokens": 0}
    r1 = charge_llm_step("tg:8", u, state_id="s", step=2, call_index=1, credit_service=credits_simple)
    r2 = charge_llm_step("tg:8", u, state_id="s", step=2, call_index=1, credit_service=credits_simple)
    assert r1["charged"] and r2["charged"]
    assert credits_simple.get_wallet("tg:8").current_balance == 50 - r1["credits"]


def test_charge_llm_step_insufficient_raises(credits_simple):
    credits_simple.credit_credits("tg:9", 1, idempotency_key="fund-tg9-001")
    with pytest.raises(InsufficientCreditsError) as ei:
        charge_llm_step(
            "tg:9",
            {"prompt_tokens": 5000, "completion_tokens": 5000},
            state_id="s",
            step=3,
            call_index=1,
            credit_service=credits_simple,
        )
    assert ei.value.needed > 1
    assert ei.value.tenant_id == "tg:9"


def test_charge_skipped_when_disabled(credits_simple, monkeypatch):
    monkeypatch.setenv("LUMEN_LIVE_LLM_CHARGE", "0")
    credits_simple.credit_credits("tg:10", 10, idempotency_key="fund-tg10-001")
    r = charge_llm_step(
        "tg:10",
        {"prompt_tokens": 2000, "completion_tokens": 2000},
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
        {"prompt_tokens": 1000, "completion_tokens": 100},
        state_id="s",
        step=1,
        call_index=1,
        credit_service=credits_simple,
    )
    assert r["skipped"] is True
    assert r["reason"] == "no_tenant"


def test_bound_context_charges_and_raises(credits_simple):
    credits_simple.credit_credits("tg:55", 2, idempotency_key="fund-tg55-001")
    tok = bind_charge_context(tenant_id="tg:55", state_id="run-x", step=1, call_index=0)
    try:
        # 1500 prompt → 2 credits
        r = charge_bound_usage(
            {"prompt_tokens": 1500, "completion_tokens": 0},
            provider="openai",
            model_id="test",
            credit_service=credits_simple,
        )
        assert r and r["charged"]
        assert credits_simple.get_wallet("tg:55").current_balance == 0
        with pytest.raises(InsufficientCreditsError):
            charge_bound_usage(
                {"prompt_tokens": 1500, "completion_tokens": 0},
                provider="openai",
                model_id="test",
                credit_service=credits_simple,
            )
    finally:
        clear_charge_context(tok)


def test_decide_charges_via_bound_context(credits_simple, monkeypatch):
    """decide() must charge when context is bound (source-level root fix)."""
    from lumen.engine.services.cline_runtime import agent_brain

    credits_simple.credit_credits("tg:77", 3, idempotency_key="fund-tg77-001")

    def fake_invoke(choice, system, user, task="build"):
        agent_brain._record_usage("openai", "gpt-test", {
            "usage": {"prompt_tokens": 1000, "completion_tokens": 0, "total_tokens": 1000}
        })
        return '{"thought":"t","tool":"list_dir","args":{"path":"."}}'

    monkeypatch.setattr(agent_brain, "_invoke_choice", fake_invoke)
    monkeypatch.setattr(
        agent_brain,
        "select_model",
        lambda task="build": type("C", (), {"provider": "openai", "model_id": "gpt-test"})(),
    )
    monkeypatch.setenv("CLINE_DECISION_CACHE", "0")

    tok = bind_charge_context(tenant_id="tg:77", state_id="dec-1", step=0, call_index=0)
    try:
        d = agent_brain.decide(
            [{"role": "user", "content": "hi"}],
            choice=type("C", (), {"provider": "openai", "model_id": "gpt-test"})(),
        )
        assert d.get("credit_charge", {}).get("charged") is True
        assert credits_simple.get_wallet("tg:77").current_balance == 3 - 1
    finally:
        clear_charge_context(tok)


def test_decide_raises_insufficient(credits_simple, monkeypatch):
    from lumen.engine.services.cline_runtime import agent_brain

    credits_simple.credit_credits("tg:78", 1, idempotency_key="fund-tg78-001")

    def fake_invoke(choice, system, user, task="build"):
        agent_brain._record_usage("openai", "gpt-test", {
            "usage": {"prompt_tokens": 5000, "completion_tokens": 5000, "total_tokens": 10000}
        })
        return '{"thought":"t","tool":"list_dir","args":{"path":"."}}'

    monkeypatch.setattr(agent_brain, "_invoke_choice", fake_invoke)
    monkeypatch.setattr(
        agent_brain,
        "select_model",
        lambda task="build": type("C", (), {"provider": "openai", "model_id": "gpt-test"})(),
    )
    monkeypatch.setenv("CLINE_DECISION_CACHE", "0")

    tok = bind_charge_context(tenant_id="tg:78", state_id="dec-2", step=1, call_index=0)
    try:
        with pytest.raises(InsufficientCreditsError):
            agent_brain.decide(
                [{"role": "user", "content": "hi"}],
                choice=type("C", (), {"provider": "openai", "model_id": "gpt-test"})(),
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
    assert reason2 == "insufficient_balance"


def test_user_facing_insufficient_message(monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "test")
    monkeypatch.setenv("TBE_ENV", "test")
    # Import module file directly to avoid bot package secrets boot
    import importlib.util
    from pathlib import Path as P
    path = P("lumen/bot/sanitize.py")
    spec = importlib.util.spec_from_file_location("lumen_bot_sanitize_test", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    msg = mod.user_facing_generation_error(code="insufficient_credits:needed=5")
    assert "insufficient_credits" in msg
    assert "رصيد" in msg


def test_agent_loop_stops_on_insufficient_credits(credits_simple, monkeypatch):
    """Balance for one small step only → loop stops with insufficient_credits."""
    from lumen.engine.services.cline_runtime import agent_loop
    from lumen.platform.credits.llm_live import InsufficientCreditsError as ICE

    credits_simple.credit_credits("tg:99", 2, idempotency_key="fund-tg99-001")
    monkeypatch.setenv("CLINE_AGENT_MAX_STEPS", "5")
    monkeypatch.setenv("CLINE_LLM_RETRIES", "1")
    monkeypatch.setenv("CLINE_DECISION_CACHE", "0")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-live-charge")
    monkeypatch.setenv("CLINE_ROUTER", "local")

    call_count = {"n": 0}

    def fake_decide(messages, **kwargs):
        call_count["n"] += 1
        # Simulate source-level charge (as real decide would)
        from lumen.platform.credits.llm_live import charge_bound_usage

        usage = {
            "prompt_tokens": 1500,
            "completion_tokens": 0,
            "provider": "openai",
            "model_id": "gpt-test",
        }
        receipt = charge_bound_usage(usage, provider="openai", model_id="gpt-test", credit_service=credits_simple)
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
            "usage": usage,
            "cache_hit": False,
            "credit_charge": receipt,
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
    monkeypatch.setattr(
        "lumen.engine.services.cline_runtime.agent_loop.describe_runtime",
        lambda: {"provider": "openai", "model_id": "gpt-test"},
    )

    import tempfile

    with tempfile.TemporaryDirectory() as td:
        # First step: 2 credits charged. Second decide will raise via charge_bound_usage
        # Override fake_decide to raise on second call
        def fake_decide_stop(messages, **kwargs):
            call_count["n"] += 1
            from lumen.platform.credits.llm_live import charge_bound_usage

            usage = {
                "prompt_tokens": 1500,
                "completion_tokens": 0,
                "provider": "openai",
                "model_id": "gpt-test",
            }
            receipt = charge_bound_usage(
                usage, provider="openai", model_id="gpt-test", credit_service=credits_simple
            )
            return {
                "thought": "step",
                "tool": "list_dir",
                "args": {"path": "."},
                "parse_ok": True,
                "provider": "openai",
                "model_id": "gpt-test",
                "usage": usage,
                "cache_hit": False,
                "credit_charge": receipt,
                "finish": False,
                "args": {"path": "."},
            }

        monkeypatch.setattr(agent_loop, "decide", fake_decide_stop)
        state = agent_loop.run_agent(
            work_dir=td,
            goal="list files only",
            ir_dict={"user_id": 99},
            max_steps=5,
        )

    assert state.stop_reason == "insufficient_credits"
    assert state.ok is False
    assert any("insufficient_credits" in e for e in (state.errors or []))
    assert credits_simple.get_wallet("tg:99").current_balance == 0
    assert call_count["n"] <= 2
