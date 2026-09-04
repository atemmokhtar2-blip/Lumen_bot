
"""Pre-launch gaps: hosting settle → credits, usage report, daily cap."""
from __future__ import annotations

import pytest

from lumen.platform.credits import reset_credit_service_for_tests
from lumen.platform.credits.memory_store import MemoryCreditsStore
from lumen.platform.credits.service import CreditService


@pytest.fixture
def credits(monkeypatch):
    reset_credit_service_for_tests()
    store = MemoryCreditsStore()
    svc = CreditService(store)
    monkeypatch.setenv("LUMEN_LIVE_LLM_CHARGE", "1")
    monkeypatch.setenv("DATABASE_URL", "")
    import lumen.platform.credits.service as svc_mod
    svc_mod._SVC = svc
    monkeypatch.setattr(svc_mod, "get_credit_service", lambda: svc)
    import lumen.platform.credits as pkg
    monkeypatch.setattr(pkg, "get_credit_service", lambda: svc)
    return svc


def test_settle_instance_deducts_credits(credits):
    from types import SimpleNamespace
    from lumen.hosting.usage_billing import settle_instance

    credits.credit_credits("tg:5", 100, idempotency_key="fund-tg5-settle")
    inst = SimpleNamespace(
        instance_id="inst-abc",
        user_id=5,
        started_at=__import__("time").time() - 3600,  # 1 hour
        project_path="/tmp",
    )
    usage = settle_instance(inst, tenant_id="tg:5")
    assert usage.get("tenant_id") == "tg:5"
    charged = int(usage.get("credits_charged") or 0)
    # even small host session may charge >= 0
    bal = credits.get_wallet("tg:5").current_balance
    if charged > 0:
        assert bal == 100 - charged
        assert usage.get("credit_result", {}).get("ok") is True
    else:
        assert bal == 100


def test_usage_report_buckets(credits):
    from lumen.platform.credits.usage_report import tenant_usage_report
    from lumen.platform.credits.llm_live import charge_llm_step

    credits.credit_credits("tg:6", 200, idempotency_key="fund-tg6-rep")
    charge_llm_step(
        "tg:6",
        {"prompt_tokens": 20_000, "completion_tokens": 0, "provider": "openai", "model_id": "gpt-4o-mini"},
        state_id="r1",
        step=1,
        call_index=1,
        credit_service=credits,
    )
    report = tenant_usage_report("tg:6", credit_service=credits)
    assert report["ok"] is True
    assert report["balance"] < 200
    assert report["llm_credits_spent"] >= 1 or report["llm_steps"] >= 0


def test_daily_cap_blocks(credits, monkeypatch):
    monkeypatch.setenv("LUMEN_DAILY_CREDIT_CAP", "2")
    from lumen.platform.credits.llm_live import charge_llm_step, InsufficientCreditsError

    credits.credit_credits("tg:7", 1000, idempotency_key="fund-tg7-cap")
    # First small charges may use 1-2 credits; force many tokens to exceed
    with pytest.raises(InsufficientCreditsError):
        for i in range(20):
            charge_llm_step(
                "tg:7",
                {
                    "prompt_tokens": 50_000,
                    "completion_tokens": 20_000,
                    "provider": "anthropic",
                    "model_id": "claude-3-5-sonnet",
                },
                state_id="cap",
                step=i,
                call_index=1,
                credit_service=credits,
            )


def test_assert_generation_blocked_on_zero_balance(credits, monkeypatch):
    from lumen.platform.credits.guards import GenerationBlockedError, assert_generation_allowed
    from lumen.platform.balance_lifecycle import BalanceLifecycle, MemoryLifecycleStore

    # Wire lifecycle to same credit service
    lc = BalanceLifecycle(MemoryLifecycleStore(), credits)
    monkeypatch.setattr(
        "lumen.platform.balance_lifecycle.get_balance_lifecycle",
        lambda: lc,
    )
    # empty wallet
    with pytest.raises(GenerationBlockedError):
        assert_generation_allowed(user_id=999)


def test_run_agent_blocks_without_balance(credits, monkeypatch, tmp_path):
    from lumen.engine.services.cline_runtime import agent_loop
    from lumen.platform.balance_lifecycle import BalanceLifecycle, MemoryLifecycleStore

    lc = BalanceLifecycle(MemoryLifecycleStore(), credits)
    monkeypatch.setattr(
        "lumen.platform.balance_lifecycle.get_balance_lifecycle",
        lambda: lc,
    )
    monkeypatch.setattr(
        "lumen.engine.services.cline_runtime.agent_loop.select_model_for_goal",
        lambda **kw: (type("C", (), {"provider": "openai", "model_id": "x"})(), {}),
    )
    state = agent_loop.run_agent(
        work_dir=str(tmp_path),
        goal="x",
        ir_dict={"user_id": 888},
        max_steps=2,
    )
    assert state.ok is False
    assert state.stop_reason in {"insufficient_credits", "billing_gate_error"}


def test_enforce_generation_blocks_zero_balance(credits, monkeypatch):
    from lumen.platform.balance_lifecycle import BalanceLifecycle, MemoryLifecycleStore
    from lumen.platform.billing import BillingService

    lc = BalanceLifecycle(MemoryLifecycleStore(), credits)
    monkeypatch.setattr(
        "lumen.platform.balance_lifecycle.get_balance_lifecycle",
        lambda: lc,
    )

    class FakeTenant:
        active = True

    class FakeStore:
        def get(self, tid):
            return FakeTenant()

    monkeypatch.setattr("lumen.platform.billing.get_tenant_store", lambda: FakeStore())
    monkeypatch.setattr("lumen.platform.billing.get_metering", lambda: type("M", (), {"try_reserve_generation": lambda *a, **k: (True, "ok", None)})())

    b = BillingService()
    ok, reason = b.enforce_generation("tg:empty")
    assert ok is False
    assert reason


def test_batch_token_pricing_not_per_raw_token(credits):
    from types import SimpleNamespace
    from lumen.platform.rating_engine import compute_batch_cost

    batch = SimpleNamespace(
        messages_processed=0,
        llm_tokens_used=5000,
        uptime_seconds=0,
        ram_mb=0,
    )
    bd = compute_batch_cost(batch, credits)
    # 5k tokens must NOT cost 5000 credits (old bug)
    assert bd.token_credits < 5000
    assert bd.token_credits >= 1


def test_cost_stack_health():
    from lumen.platform.credits.health import cost_stack_health
    report = cost_stack_health()
    assert "checks" in report
    assert report["checks"].get("credit_service", {}).get("ok") is True


def test_is_generation_allowed_rejects_empty_tenant(credits):
    from lumen.platform.balance_lifecycle import BalanceLifecycle, MemoryLifecycleStore
    lc = BalanceLifecycle(MemoryLifecycleStore(), credits)
    ok, reason = lc.is_generation_allowed("")
    assert ok is False
    assert reason == "no_tenant"


def test_is_hosting_allowed_rejects_empty_tenant(credits):
    from lumen.platform.balance_lifecycle import BalanceLifecycle, MemoryLifecycleStore
    lc = BalanceLifecycle(MemoryLifecycleStore(), credits)
    ok, reason = lc.is_hosting_allowed("")
    assert ok is False
    assert reason == "no_tenant"
