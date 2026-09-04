"""Tenant cost/usage report — developer-facing summary from the credits ledger.

Closes the gap: no dashboard for LLM + hosting spend.
"""
from __future__ import annotations

import time
from typing import Any


def tenant_usage_report(tenant_id: str, *, limit: int = 200, credit_service: Any = None) -> dict[str, Any]:
    """Aggregate ledger into LLM / hosting / topup buckets + current balance."""
    tid = str(tenant_id or "").strip()
    if not tid:
        return {"ok": False, "error": "tenant_id_required"}
    if credit_service is None:
        from lumen.platform.credits import get_credit_service
        credit_service = get_credit_service()

    wallet = credit_service.get_wallet(tid)
    entries = list(credit_service.list_ledger(tid, limit=int(limit) or 200) or [])

    llm_spent = 0
    host_spent = 0
    other_spent = 0
    topped_up = 0
    llm_steps = 0
    host_settles = 0
    recent: list[dict[str, Any]] = []

    for e in entries:
        et = str(getattr(e, "type", None) or getattr(e, "type_", None) or "")
        # amount may be on legs or amount field
        amount = 0
        legs = getattr(e, "legs", None) or []
        for leg in legs:
            try:
                amt = abs(int(getattr(leg, "amount", 0) or 0))
                side = str(getattr(leg, "side", "") or "").lower()
                if amt <= 0:
                    continue
                # Prefer the leg that moves the user wallet
                if side in {"debit", "credit"}:
                    amount = amt
                    if side == "debit" and et in {"llm_step", "llm_usage", "host_usage", "generation_cost"}:
                        break
                    if side == "credit" and et in {"purchase", "topup", "stripe_credit", "welcome", "credit"}:
                        break
            except (TypeError, ValueError):
                pass
        meta = getattr(e, "metadata", None) or {}
        if not isinstance(meta, dict):
            meta = {}
        row = {
            "type": et,
            "amount": amount,
            "ts": getattr(e, "created_at", None) or getattr(e, "ts", None),
            "reference_id": getattr(e, "reference_id", "") or "",
            "metadata": {k: meta.get(k) for k in list(meta)[:8]},
        }
        recent.append(row)
        if et in {"llm_step", "llm_usage"}:
            llm_spent += amount
            llm_steps += 1
        elif et in {"host_usage", "host_session"}:
            host_spent += amount
            host_settles += 1
        elif et in {"purchase", "topup", "stripe_credit", "welcome", "credit"}:
            topped_up += amount
        elif et and amount and et not in {"reserve", "release", "capture"}:
            other_spent += amount

    return {
        "ok": True,
        "tenant_id": tid,
        "balance": int(getattr(wallet, "current_balance", 0) or 0),
        "reserved": int(getattr(wallet, "reserved_balance", 0) or 0),
        "llm_credits_spent": int(llm_spent),
        "llm_steps": int(llm_steps),
        "hosting_credits_spent": int(host_spent),
        "host_settles": int(host_settles),
        "other_spent": int(other_spent),
        "topped_up": int(topped_up),
        "entries_sampled": len(entries),
        "recent": recent[:50],
        "generated_at": time.time(),
        "billing_model": "credits_only",
        "note": "Spend is model-aware LLM + host session settle; not a fixed generation fee.",
    }


__all__ = ["tenant_usage_report"]
