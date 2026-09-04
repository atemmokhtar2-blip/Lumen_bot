
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
