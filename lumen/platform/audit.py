"""Phase 5 — credits audit & reconciliation (read-only).

Builds tenant-facing and admin audit views over CreditService + ratings + lifecycle.
Never mutates balances.
"""
from __future__ import annotations

import logging
from typing import Any, Optional

logger = logging.getLogger(__name__)


def _entry_to_dict(e: Any) -> dict[str, Any]:
    legs = []
    for leg in getattr(e, "legs", None) or []:
        legs.append(
            {
                "account_id": getattr(leg, "account_id", ""),
                "side": getattr(leg, "side", ""),
                "amount": int(getattr(leg, "amount", 0) or 0),
            }
        )
    return {
        "transaction_id": getattr(e, "transaction_id", ""),
        "tenant_id": getattr(e, "tenant_id", ""),
        "type": getattr(e, "type", ""),
        "amount": int(getattr(e, "amount", 0) or 0),
        "balance_after": int(getattr(e, "balance_after", 0) or 0),
        "reserved_after": int(getattr(e, "reserved_after", 0) or 0),
        "reference_id": getattr(e, "reference_id", ""),
        "idempotency_key": getattr(e, "idempotency_key", ""),
        "entry_hash": getattr(e, "entry_hash", ""),
        "prev_hash": getattr(e, "prev_hash", ""),
        "legs": legs,
        "metadata": dict(getattr(e, "metadata", None) or {}),
        "created_at": float(getattr(e, "created_at", 0) or 0),
    }


def ledger_audit(
    credit_service: Any,
    tenant_id: str,
    *,
    limit: int = 100,
    type_filter: str = "",
) -> dict[str, Any]:
    rows = credit_service.list_ledger(str(tenant_id), limit=min(500, max(1, int(limit))))
    if type_filter:
        rows = [e for e in rows if getattr(e, "type", "") == type_filter]
    entries = [_entry_to_dict(e) for e in rows]
    # idempotency uniqueness check within page
    keys = [e["idempotency_key"] for e in entries if e.get("idempotency_key")]
    dup_keys = sorted({k for k in keys if keys.count(k) > 1})
    # hash chain check (oldest→newest within page reversed list)
    chronological = list(reversed(entries))
    chain_ok = True
    chain_breaks = []
    for i in range(1, len(chronological)):
        prev_h = chronological[i - 1].get("entry_hash") or ""
        cur_prev = chronological[i].get("prev_hash") or ""
        if prev_h and cur_prev and prev_h != cur_prev:
            chain_ok = False
            chain_breaks.append(chronological[i].get("transaction_id"))
    return {
        "tenant_id": str(tenant_id),
        "count": len(entries),
        "entries": entries,
        "idempotency_duplicates_in_page": dup_keys,
        "hash_chain_ok": chain_ok,
        "hash_chain_breaks": chain_breaks[:20],
    }


def reconcile_tenant(credit_service: Any, tenant_id: str) -> dict[str, Any]:
    rep = credit_service.reconcile(str(tenant_id))
    wallet = credit_service.get_wallet(str(tenant_id))
    out = {
        "tenant_id": str(tenant_id),
        "ok": bool(getattr(rep, "ok", False)),
        "wallet_balance": int(getattr(rep, "wallet_balance", wallet.current_balance) or 0),
        "ledger_wallet_net": int(getattr(rep, "ledger_wallet_net", 0) or 0),
        "wallet_reserved": int(getattr(rep, "wallet_reserved", wallet.reserved_balance) or 0),
        "drift_balance": int(getattr(rep, "drift_balance", 0) or 0),
        "unbalanced_transactions": int(getattr(rep, "unbalanced_transactions", 0) or 0),
        "available": int(wallet.available),
    }
    if hasattr(rep, "notes"):
        out["notes"] = getattr(rep, "notes") or ""
    return out


def tenant_overview(
    tenant_id: str,
    *,
    credit_service: Any,
    rating_engine: Optional[Any] = None,
    lifecycle: Optional[Any] = None,
    ledger_limit: int = 50,
) -> dict[str, Any]:
    tid = str(tenant_id)
    wallet = credit_service.get_wallet(tid)
    recon = reconcile_tenant(credit_service, tid)
    ledger = ledger_audit(credit_service, tid, limit=ledger_limit)
    out: dict[str, Any] = {
        "tenant_id": tid,
        "wallet": {
            "current_balance": wallet.current_balance,
            "reserved_balance": wallet.reserved_balance,
            "available": wallet.available,
            "currency": getattr(wallet, "currency", "credits"),
        },
        "reconcile": recon,
        "ledger": {
            "count": ledger["count"],
            "hash_chain_ok": ledger["hash_chain_ok"],
            "idempotency_duplicates_in_page": ledger["idempotency_duplicates_in_page"],
            "entries": ledger["entries"],
        },
        "pricing": [
            {
                "resource_type": r.resource_type,
                "cost_per_unit": r.cost_per_unit,
                "description": getattr(r, "description", ""),
            }
            for r in credit_service.list_pricing()
        ],
    }
    if rating_engine is not None:
        try:
            out["ratings"] = rating_engine.list_ratings(tid, limit=50)
            out["rating_failures"] = [
                f for f in rating_engine.list_failures(limit=100)
                if str(f.get("tenant_id") or "") == tid
            ]
        except Exception as exc:
            out["ratings_error"] = type(exc).__name__
    if lifecycle is not None:
        try:
            out["lifecycle"] = lifecycle.status(tid)
        except Exception as exc:
            out["lifecycle_error"] = type(exc).__name__
    out["audit_ok"] = bool(recon.get("ok")) and bool(ledger.get("hash_chain_ok")) and not ledger.get(
        "idempotency_duplicates_in_page"
    )
    return out
