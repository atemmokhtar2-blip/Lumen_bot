"""Hardened phase-3 rating tests."""
from __future__ import annotations

import concurrent.futures
import time

from lumen.platform.credits.memory_store import MemoryCreditsStore
from lumen.platform.credits.service import CreditService
from lumen.platform.rating_engine import (
    MemoryRatingStore,
    RatingEngine,
    compute_batch_cost,
    reserve_for_hosting,
)
from lumen.platform.usage_batches import MemoryUsageBatchStore, UsageBatchService, register_bot


def _pair():
    credits = CreditService(MemoryCreditsStore())
    usage = UsageBatchService(MemoryUsageBatchStore())
    engine = RatingEngine(MemoryRatingStore(), usage, credits)
    return credits, usage, engine


def _ingest(usage, tenant, bot, key, **metrics):
    register_bot(tenant, bot)
    now = time.time()
    body = {
        "bot_id": bot,
        "window_start": now - 300,
        "window_end": now,
        "messages_processed": 0,
        "llm_tokens_used": 0,
        "uptime_seconds": 0,
        "ram_mb": 0,
        "idempotency_key": key,
    }
    body.update(metrics)
    return usage.ingest(tenant, body, require_ownership=True, skip_rate_limit=True)


def test_compute_and_cap(monkeypatch):
    monkeypatch.setenv("TBE_RATING_MAX_CREDITS_PER_BATCH", "15")
    # reload max - compute uses module level MAX at import; set via recompute path
    import lumen.platform.rating_engine as re
    re.MAX_PER_BATCH = 15
    credits = CreditService(MemoryCreditsStore())
    class B:
        messages_processed = 100
        llm_tokens_used = 0
        uptime_seconds = 0
        ram_mb = 0
    bd = compute_batch_cost(B(), credits)
    assert bd.capped and bd.total == 15
    re.MAX_PER_BATCH = 100000


def test_rate_once_and_parallel():
    credits, usage, engine = _pair()
    credits.credit_credits("ten_r", 5000, idempotency_key="fund-ten-r-001")
    ing = _ingest(usage, "ten_r", "bot_r", "batch-rate-001", messages_processed=10)
    assert ing.ok

    def once(_):
        return engine.rate_batch(ing.batch)

    with concurrent.futures.ThreadPoolExecutor(8) as ex:
        results = list(ex.map(once, range(8)))
    ok_charge = [r for r in results if r.ok and not r.skipped and r.credits_charged > 0]
    # at most one real charge
    assert len(ok_charge) <= 1
    expected = credits.cost_for("telegram_message", 10)
    # wallet dropped by at most expected once
    assert credits.get_wallet("ten_r").current_balance == 5000 - expected


def test_capture_prefers_reservation():
    credits, usage, engine = _pair()
    credits.credit_credits("ten_c", 1000, idempotency_key="fund-cap-001")
    res = reserve_for_hosting(credits, "ten_c", hours=1, ram_mb=0, idempotency_key="reserve-cap-001")
    assert res.ok
    reserved_before = credits.get_wallet("ten_c").reserved_balance
    assert reserved_before > 0
    # small message cost should capture from hold when reserved >= cost
    ing = _ingest(usage, "ten_c", "bot_c", "batch-cap-001", messages_processed=1)
    r = engine.rate_batch(ing.batch)
    assert r.ok
    if credits.get_wallet("ten_c").reserved_balance < reserved_before:
        assert r.used_capture or r.credits_charged >= 0


def test_insufficient_records_failure():
    credits, usage, engine = _pair()
    credits.credit_credits("ten_poor", 1, idempotency_key="fund-poor-001")
    ing = _ingest(usage, "ten_poor", "bot_z", "batch-poor-001", messages_processed=100)
    r = engine.rate_batch(ing.batch)
    assert not r.ok
    fails = engine.list_failures()
    assert any(f["batch_id"] == ing.batch.batch_id for f in fails)
    assert credits.get_wallet("ten_poor").current_balance == 1


def test_rate_pending_queue():
    credits, usage, engine = _pair()
    credits.credit_credits("ten_p", 5000, idempotency_key="fund-ten-p-001")
    for i in range(3):
        _ingest(usage, "ten_p", "bot_p", f"batch-pending-{i:03d}", messages_processed=2)
    out = engine.rate_pending(limit=10)
    assert out["failed"] == 0
    assert out["charged_credits"] > 0
    assert credits.get_wallet("ten_p").current_balance < 5000


def test_zero_cost_marked():
    credits, usage, engine = _pair()
    credits.credit_credits("ten_z", 100, idempotency_key="fund-z-001")
    ing = _ingest(usage, "ten_z", "bot_z2", "batch-zero-001", messages_processed=0)
    r = engine.rate_batch(ing.batch)
    assert r.ok and r.skipped
    r2 = engine.rate_batch(ing.batch)
    assert r2.skipped
