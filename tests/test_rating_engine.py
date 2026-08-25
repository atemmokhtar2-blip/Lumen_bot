"""Phase 3 rating engine — deduct only via CreditService."""
from __future__ import annotations

import time

from b2b_platform.credits.memory_store import MemoryCreditsStore
from b2b_platform.credits.service import CreditService
from b2b_platform.rating_engine import (
    MemoryRatingStore,
    RatingEngine,
    compute_batch_cost,
    reserve_for_hosting,
)
from b2b_platform.usage_batches import MemoryUsageBatchStore, UsageBatchService, register_bot


def _svc_pair():
    credits = CreditService(MemoryCreditsStore())
    usage = UsageBatchService(MemoryUsageBatchStore())
    engine = RatingEngine(MemoryRatingStore(), usage, credits)
    return credits, usage, engine


def test_compute_cost_nonzero():
    credits = CreditService(MemoryCreditsStore())
    class B:
        messages_processed = 10
        llm_tokens_used = 5
        uptime_seconds = 3600
        ram_mb = 100
    bd = compute_batch_cost(B(), credits)
    assert bd.total > 0
    assert bd.message_credits == credits.cost_for("telegram_message", 10)


def test_rate_batch_deducts_once():
    credits, usage, engine = _svc_pair()
    credits.credit_credits("ten_r", 1000, idempotency_key="fund-ten-r-001")
    register_bot("ten_r", "bot_r")
    now = time.time()
    body = {
        "bot_id": "bot_r",
        "window_start": now - 300,
        "window_end": now,
        "messages_processed": 10,
        "llm_tokens_used": 0,
        "uptime_seconds": 0,
        "ram_mb": 0,
        "idempotency_key": "batch-rate-001",
    }
    ing = usage.ingest("ten_r", body, require_ownership=True, skip_rate_limit=True)
    assert ing.ok
    r1 = engine.rate_batch(ing.batch)
    assert r1.ok and r1.credits_charged == credits.cost_for("telegram_message", 10)
    bal = credits.get_wallet("ten_r").current_balance
    r2 = engine.rate_batch(ing.batch)
    assert r2.skipped or r2.reason == "already_rated"
    assert credits.get_wallet("ten_r").current_balance == bal  # no double charge


def test_rate_pending_processes_queue():
    credits, usage, engine = _svc_pair()
    credits.credit_credits("ten_p", 500, idempotency_key="fund-ten-p-001")
    register_bot("ten_p", "bot_p")
    now = time.time()
    for i in range(3):
        usage.ingest(
            "ten_p",
            {
                "bot_id": "bot_p",
                "window_start": now - 100,
                "window_end": now,
                "messages_processed": 2,
                "idempotency_key": f"batch-pending-{i:03d}",
            },
            require_ownership=True,
            skip_rate_limit=True,
        )
    out = engine.rate_pending(limit=10)
    assert out["processed"] == 3
    assert out["failed"] == 0
    assert credits.get_wallet("ten_p").current_balance < 500


def test_insufficient_balance_fails_rating():
    credits, usage, engine = _svc_pair()
    credits.credit_credits("ten_poor", 1, idempotency_key="fund-poor-001")
    register_bot("ten_poor", "bot_z")
    now = time.time()
    ing = usage.ingest(
        "ten_poor",
        {
            "bot_id": "bot_z",
            "window_start": now - 10,
            "window_end": now,
            "messages_processed": 100,
            "idempotency_key": "batch-poor-001",
        },
        require_ownership=True,
        skip_rate_limit=True,
    )
    r = engine.rate_batch(ing.batch)
    assert not r.ok
    assert "insufficient" in r.reason
    assert credits.get_wallet("ten_poor").current_balance == 1


def test_reserve_for_hosting():
    credits = CreditService(MemoryCreditsStore())
    credits.credit_credits("ten_h", 1000, idempotency_key="fund-host-001")
    r = reserve_for_hosting(credits, "ten_h", hours=1, ram_mb=256, idempotency_key="reserve-host-001")
    assert r.ok
    w = credits.get_wallet("ten_h")
    assert w.reserved_balance > 0
    assert w.available < 1000
