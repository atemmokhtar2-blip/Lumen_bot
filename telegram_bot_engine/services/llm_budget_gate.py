"""Hard gate before any paid LLM call — tenant/user daily token + USD caps."""
from __future__ import annotations

import logging
import os
from typing import Any

logger = logging.getLogger(__name__)


def _tenant_from_context(context: dict[str, Any] | None) -> str:
    ctx = context or {}
    for key in ("tenant_id", "user_id", "uid", "telegram_user_id"):
        val = ctx.get(key)
        if val is not None and str(val).strip():
            return str(val).strip()
    # nested
    ud = ctx.get("user_data") if isinstance(ctx.get("user_data"), dict) else {}
    if ud.get("tenant_id"):
        return str(ud["tenant_id"])
    if ctx.get("user_id") is not None:
        return f"tg:{ctx['user_id']}"
    return "anon"


def estimate_tokens(text: str, *, response_reserve: int = 2048) -> int:
    # Rough heuristic: ~4 chars per token + reserved completion budget
    return max(1, len(text or "") // 4) + max(0, int(response_reserve))


def estimate_usd(tokens: int) -> float:
    # Conservative default cost model (over-estimate to fail closed on budget)
    try:
        per_1k = float(os.getenv("LLM_USD_PER_1K_TOKENS") or "0.01")
    except ValueError:
        per_1k = 0.01
    return (max(0, int(tokens)) / 1000.0) * max(0.0, per_1k)


def gate_llm_call(
    message: str,
    context: dict[str, Any] | None = None,
    *,
    response_reserve: int = 2048,
) -> tuple[bool, str]:
    """Return (allowed, reason). On allow, reserves estimated tokens/USD."""
    try:
        from b2b_platform.rate_limit import check_tenant_llm_budget
    except Exception as exc:
        env = (os.getenv("ENVIRONMENT") or os.getenv("TBE_ENV") or "").strip().lower()
        if env not in {"dev", "development", "local", "test"}:
            logger.error("llm budget gate unavailable in production: %s", type(exc).__name__)
            return False, "llm_budget_backend_unavailable"
        return True, "budget_gate_skipped_dev"

    tenant = _tenant_from_context(context)
    tokens = estimate_tokens(message or "", response_reserve=response_reserve)
    usd = estimate_usd(tokens)
    ok, reason = check_tenant_llm_budget(tenant, add_tokens=tokens, add_usd=usd)
    if not ok:
        logger.warning("llm budget hard-cap tenant=%s reason=%s", tenant, reason)
    return ok, reason
