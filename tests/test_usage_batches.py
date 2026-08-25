"""Hardened phase-2 usage batch tests."""
from __future__ import annotations

import time

import pytest

from b2b_platform.usage_batches import (
    MemoryUsageBatchStore,
    UsageBatchService,
    content_hash_for,
    register_bot,
    reset_usage_batch_service_for_tests,
    validate_batch_payload,
)


@pytest.fixture
def svc():
    reset_usage_batch_service_for_tests()
    return UsageBatchService(MemoryUsageBatchStore())


def _body(**kw):
    base = {
        "bot_id": "bot1",
        "window_start": time.time() - 300,
        "window_end": time.time(),
        "messages_processed": 5,
        "idempotency_key": "batch-key-001234",
    }
    base.update(kw)
    return base


def test_validate_ok():
    fields, reason = validate_batch_payload(_body())
    assert reason == "ok"
    assert fields["content_hash"]


def test_reject_future_window():
    fields, reason = validate_batch_payload(_body(
        window_start=time.time() + 1000,
        window_end=time.time() + 2000,
        idempotency_key="batch-future-001",
    ))
    assert fields is None and reason == "window_in_future"


def test_reject_stale_window():
    fields, reason = validate_batch_payload(_body(
        window_start=1.0,
        window_end=2.0,
        idempotency_key="batch-stale-001",
    ))
    assert fields is None and reason == "window_too_stale"


def test_ownership_required(svc: UsageBatchService):
    r = svc.ingest("ten_1", _body(idempotency_key="batch-own-001"), require_ownership=True, skip_rate_limit=True)
    assert not r.ok and r.reason == "bot_not_registered_for_tenant"
    register_bot("ten_1", "bot1")
    r2 = svc.ingest("ten_1", _body(idempotency_key="batch-own-002"), require_ownership=True, skip_rate_limit=True)
    assert r2.ok


def test_idempotent_and_hash(svc: UsageBatchService):
    register_bot("ten_1", "bot1")
    body = _body(idempotency_key="batch-idem-001")
    a = svc.ingest("ten_1", body, require_ownership=True, skip_rate_limit=True)
    b = svc.ingest("ten_1", body, require_ownership=True, skip_rate_limit=True)
    assert a.ok and b.replay
    assert a.batch.content_hash == b.batch.content_hash
    fields, _ = validate_batch_payload(body)
    assert a.batch.content_hash == content_hash_for(fields)


def test_tenant_isolation(svc: UsageBatchService):
    register_bot("ten_a", "botB")
    svc.ingest("ten_a", _body(bot_id="botB", idempotency_key="batch-iso-001"), require_ownership=True, skip_rate_limit=True)
    assert svc.list_batches("ten_b") == []
    assert len(svc.list_batches("ten_a")) == 1


def test_no_credit_side_effect(svc: UsageBatchService):
    from b2b_platform.credits.memory_store import MemoryCreditsStore
    from b2b_platform.credits.service import CreditService
    credits = CreditService(MemoryCreditsStore())
    credits.credit_credits("ten_x", 100, idempotency_key="fund-ten-x-001")
    register_bot("ten_x", "b")
    svc.ingest("ten_x", _body(bot_id="b", messages_processed=999, idempotency_key="batch-nodeduct-001"),
               require_ownership=True, skip_rate_limit=True)
    assert credits.get_wallet("ten_x").current_balance == 100


def test_heartbeat_registers_and_emits(monkeypatch):
    monkeypatch.setenv("TBE_USAGE_RELAX_OWNERSHIP", "0")
    reset_usage_batch_service_for_tests()
    from telegram_bot_engine.services.usage.heartbeat import emit_host_heartbeat
    r = emit_host_heartbeat(tenant_id="ten_h", bot_id="bot_h", uptime_seconds=60, ram_mb=128)
    assert r.get("ok") is True
    r2 = emit_host_heartbeat(tenant_id="ten_h", bot_id="bot_h", uptime_seconds=60, ram_mb=128)
    assert r2.get("replay") is True
