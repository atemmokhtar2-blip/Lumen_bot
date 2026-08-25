"""Phase 5 audit & reconcile tests."""
from __future__ import annotations

from lumen.platform.audit import ledger_audit, reconcile_tenant, tenant_overview
from lumen.platform.credits.memory_store import MemoryCreditsStore
from lumen.platform.credits.service import CreditService


def test_ledger_and_reconcile():
    svc = CreditService(MemoryCreditsStore())
    svc.credit_credits("ten_a", 100, idempotency_key="fund-ten-a-001")
    svc.deduct_credits("ten_a", 30, idempotency_key="deduct-ten-a-001")
    led = ledger_audit(svc, "ten_a", limit=50)
    assert led["count"] >= 2
    assert led["hash_chain_ok"] is True
    assert led["idempotency_duplicates_in_page"] == []
    rec = reconcile_tenant(svc, "ten_a")
    assert rec["ok"] is True
    assert rec["wallet_balance"] == 70
    assert rec["drift_balance"] == 0


def test_overview_audit_ok():
    svc = CreditService(MemoryCreditsStore())
    svc.credit_credits("ten_b", 50, idempotency_key="fund-ten-b-001")
    ov = tenant_overview("ten_b", credit_service=svc)
    assert ov["audit_ok"] is True
    assert ov["wallet"]["current_balance"] == 50
    assert len(ov["pricing"]) >= 1


def test_type_filter():
    svc = CreditService(MemoryCreditsStore())
    svc.credit_credits("ten_c", 20, idempotency_key="fund-ten-c-001", reason="purchase")
    svc.deduct_credits("ten_c", 5, idempotency_key="deduct-ten-c-001", reason="usage_batch")
    only = ledger_audit(svc, "ten_c", type_filter="purchase")
    assert all(e["type"] == "purchase" for e in only["entries"])
