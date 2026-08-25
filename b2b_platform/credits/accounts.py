"""Chart of accounts for credit double-entry."""
from __future__ import annotations

SYSTEM_TREASURY = "system:treasury"
SYSTEM_REVENUE = "system:revenue"
SYSTEM_HOLDS = "system:holds"
MAX_AMOUNT = 1_000_000_000_000  # 1e12 credits hard cap per op


def user_wallet_account(tenant_id: str) -> str:
    return f"wallet:{tenant_id}"


def validate_amount(amount: int) -> str | None:
    if not isinstance(amount, int) or isinstance(amount, bool):
        return "amount_must_be_int"
    if amount <= 0:
        return "amount_must_be_positive"
    if amount > MAX_AMOUNT:
        return "amount_exceeds_max"
    return None


def validate_idempotency_key(key: str) -> str | None:
    k = (key or "").strip()
    if len(k) < 8:
        return "idempotency_key_too_short"
    if len(k) > 200:
        return "idempotency_key_too_long"
    return None
