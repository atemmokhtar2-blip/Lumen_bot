"""Phase 2 usage batch tests — no credit deduction."""
from __future__ import annotations

from b2b_platform.usage_batches import (
    MemoryUsageBatchStore,
    UsageBatchService,
    validate_batch_payload,
)


def test_validate_ok():
    fields, reason = validate_batch_payload({
        "bot_id": "bot1",
        "window_start": 100.0,
        "window_end": 400.0,
        "messages_processed": 5,
        "idempotency_key": "batch-key-001",
    })
    assert reason == "ok" and fields["messages_processed"] == 5


def test_validate_rejects_short_key():
    fields, reason = validate_batch_payload({
        "bot_id": "bot1", "window_start": 1, "window_end": 2, "idempotency_key": "short",
    })
    assert fields is None and reason == "idempotency_key_invalid"


def test_ingest_and_idempotent():
    svc = UsageBatchService(MemoryUsageBatchStore())
    body = {
        "bot_id": "botA",
        "window_start": 1000.0,
        "window_end": 1300.0,
        "messages_processed": 3,
        "llm_tokens_used": 10,
        "uptime_seconds": 300,
        "idempotency_key": "batch-botA-1300",
    }
    a = svc.ingest("ten_1", body)
    b = svc.ingest("ten_1", body)
    assert a.ok and not a.replay
    assert b.ok and b.replay
    assert a.batch.batch_id == b.batch.batch_id
    rows = svc.list_batches("ten_1")
    assert len(rows) == 1
    assert rows[0].status == "accepted"


def test_tenant_isolation():
    svc = UsageBatchService(MemoryUsageBatchStore())
    body = {
        "bot_id": "botB",
        "window_start": 1.0,
        "window_end": 2.0,
        "idempotency_key": "batch-iso-001",
    }
    svc.ingest("ten_a", body)
    assert svc.list_batches("ten_b") == []
    assert len(svc.list_batches("ten_a")) == 1


def test_no_credit_side_effect():
    from b2b_platform.credits.memory_store import MemoryCreditsStore
    from b2b_platform.credits.service import CreditService
    credits = CreditService(MemoryCreditsStore())
    credits.credit_credits("ten_x", 100, idempotency_key="fund-ten-x-001")
    svc = UsageBatchService(MemoryUsageBatchStore())
    svc.ingest("ten_x", {
        "bot_id": "b",
        "window_start": 1,
        "window_end": 2,
        "messages_processed": 999,
        "idempotency_key": "batch-nodeduct-001",
    })
    assert credits.get_wallet("ten_x").current_balance == 100


def test_heartbeat_helper():
    from telegram_bot_engine.services.usage.heartbeat import emit_host_heartbeat
    r = emit_host_heartbeat(tenant_id="ten_h", bot_id="bot_h", uptime_seconds=60, ram_mb=128)
    assert r.get("ok") is True
    r2 = emit_host_heartbeat(tenant_id="ten_h", bot_id="bot_h", uptime_seconds=60, ram_mb=128)
    assert r2.get("replay") is True
