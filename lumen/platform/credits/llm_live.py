"""Live per-step LLM cost charging — root-cause metering for agent loops.

After every real provider call the agent records token usage. This module
converts that usage into integer credits via pricing rules and deducts them
from the tenant wallet with an idempotent key.

If the wallet cannot cover the step, InsufficientCreditsError is raised so
agent_loop / orchestrator can stop immediately with a clear reason.

Design rules:
  - Real credits path only (CreditService double-entry). No fake counters.
  - Idempotent: same (tenant, state_id, step, call_index) never double-charges.
  - Kill switch: LUMEN_LIVE_LLM_CHARGE=0 disables charging (tests / emergency).
  - Anonymous / user_id=0 skips charge (local probes, health checks).
  - Pricing prefers llm_prompt_1k / llm_completion_1k; falls back to USD→credits.
"""
from __future__ import annotations

import logging
import math
import os
from typing import Any, Optional

logger = logging.getLogger("lumen.credits.llm_live")


class InsufficientCreditsError(Exception):
    """Raised when a live LLM step cannot be paid from the tenant wallet."""

    def __init__(
        self,
        tenant_id: str,
        *,
        needed: int = 0,
        available: int = 0,
        reason: str = "insufficient_balance",
        step: int = 0,
    ) -> None:
        self.tenant_id = str(tenant_id or "")
        self.needed = int(needed or 0)
        self.available = int(available or 0)
        self.reason = str(reason or "insufficient_balance")
        self.step = int(step or 0)
        super().__init__(
            f"insufficient_credits tenant={self.tenant_id} "
            f"needed={self.needed} available={self.available} "
            f"reason={self.reason} step={self.step}"
        )


def live_charge_enabled() -> bool:
    return (os.getenv("LUMEN_LIVE_LLM_CHARGE") or "1").strip().lower() not in {
        "0", "false", "no", "off",
    }


def tenant_id_from_user(user_id: int | str | None) -> str:
    """Canonical tenant key used across bot + budget gates (tg:{id})."""
    try:
        uid = int(user_id or 0)
    except (TypeError, ValueError):
        uid = 0
    if uid <= 0:
        return ""
    return f"tg:{uid}"


def credits_for_llm_usage(usage: dict[str, Any] | None, *, credit_service: Any = None) -> int:
    """Convert provider usage dict → integer credits (never fractional).

    Order of preference:
      1) llm_prompt_1k + llm_completion_1k pricing rules (ceil per 1k tokens)
      2) estimate_cost_usd × LUMEN_CREDITS_PER_USD (default 100)
      3) 0 when usage is empty
    """
    u = dict(usage or {})
    prompt = int(u.get("prompt_tokens") or u.get("prompt_tokens_est") or 0)
    completion = int(u.get("completion_tokens") or 0)
    if prompt <= 0 and completion <= 0:
        total = int(u.get("total_tokens") or 0)
        if total <= 0:
            return 0
        # Unknown split — same 70/30 used by cost_model
        prompt = int(total * 0.7)
        completion = max(0, total - prompt)

    if credit_service is None:
        try:
            from lumen.platform.credits import get_credit_service

            credit_service = get_credit_service()
        except Exception:
            credit_service = None

    credits = 0
    used_rules = False
    if credit_service is not None:
        try:
            p_units = (prompt + 999) // 1000 if prompt > 0 else 0
            c_units = (completion + 999) // 1000 if completion > 0 else 0
            p_cost = int(credit_service.cost_for("llm_prompt_1k", p_units)) if p_units else 0
            c_cost = int(credit_service.cost_for("llm_completion_1k", c_units)) if c_units else 0
            # cost_for returns 0 when rule missing — treat as "rules present" only if >0 total
            # or rule exists
            rules = {r.resource_type for r in (credit_service.list_pricing() or [])}
            if "llm_prompt_1k" in rules or "llm_completion_1k" in rules:
                credits = p_cost + c_cost
                used_rules = True
        except Exception:
            logger.debug("pricing rules path failed", exc_info=True)
            used_rules = False

    if not used_rules:
        try:
            from lumen.engine.services.evaluation.cost_model import estimate_cost_usd

            usd = float(estimate_cost_usd(u) or 0.0)
        except Exception:
            usd = 0.0
        try:
            rate = float(os.getenv("LUMEN_CREDITS_PER_USD") or "100")
        except ValueError:
            rate = 100.0
        rate = max(0.0, rate)
        credits = int(math.ceil(usd * rate)) if usd > 0 and rate > 0 else 0

    if credits <= 0 and (prompt > 0 or completion > 0):
        # Floor: any real token traffic costs at least 1 credit
        credits = 1
    return max(0, int(credits))


def charge_llm_step(
    tenant_id: str,
    usage: dict[str, Any] | None,
    *,
    state_id: str = "",
    step: int = 0,
    call_index: int = 0,
    provider: str = "",
    model_id: str = "",
    credit_service: Any = None,
) -> dict[str, Any]:
    """Deduct credits for one LLM step. Raises InsufficientCreditsError on fail.

    Returns a small receipt dict always when charging is skipped or succeeds.
    """
    tid = str(tenant_id or "").strip()
    receipt: dict[str, Any] = {
        "charged": False,
        "credits": 0,
        "skipped": False,
        "reason": "ok",
        "tenant_id": tid,
        "step": int(step or 0),
    }

    if not live_charge_enabled():
        receipt["skipped"] = True
        receipt["reason"] = "live_charge_disabled"
        return receipt
    if not tid:
        receipt["skipped"] = True
        receipt["reason"] = "no_tenant"
        return receipt

    amount = credits_for_llm_usage(usage, credit_service=credit_service)
    receipt["credits"] = amount
    if amount <= 0:
        receipt["skipped"] = True
        receipt["reason"] = "zero_usage"
        return receipt

    if credit_service is None:
        from lumen.platform.credits import get_credit_service

        credit_service = get_credit_service()

    sid = str(state_id or "").strip() or "nostate"
    idem = f"llm:{tid}:{sid}:{int(step)}:{int(call_index)}"
    # Keep key within typical store limits
    if len(idem) > 180:
        idem = idem[:180]

    meta = {
        "provider": str(provider or ""),
        "model_id": str(model_id or ""),
        "step": int(step or 0),
        "call_index": int(call_index or 0),
        "usage": {
            k: usage.get(k)
            for k in (
                "prompt_tokens",
                "completion_tokens",
                "total_tokens",
                "prompt_tokens_est",
                "estimated",
                "provider",
                "model_id",
            )
            if isinstance(usage, dict) and usage.get(k) is not None
        },
    }

    result = credit_service.deduct_credits(
        tid,
        amount,
        reason="llm_step",
        reference_id=sid,
        idempotency_key=idem,
        metadata=meta,
    )
    if not result.ok:
        available = 0
        try:
            w = credit_service.get_wallet(tid)
            available = int(getattr(w, "available", 0) or 0)
        except Exception:
            pass
        raise InsufficientCreditsError(
            tid,
            needed=amount,
            available=available,
            reason=str(result.reason or "insufficient_balance"),
            step=int(step or 0),
        )

    receipt["charged"] = True
    receipt["transaction_id"] = getattr(result, "transaction_id", "") or ""
    receipt["reason"] = "ok"

    # Drive balance lifecycle (warning → grace → suspend)
    try:
        from lumen.platform.balance_lifecycle import get_balance_lifecycle

        get_balance_lifecycle().on_balance_changed(tid)
    except Exception:
        logger.debug("balance lifecycle after llm charge skipped", exc_info=True)

    # Keep daily LLM budget counters in sync (tokens)
    try:
        from lumen.platform.rate_limit import check_tenant_llm_budget

        toks = 0
        if isinstance(usage, dict):
            toks = int(
                usage.get("total_tokens")
                or (
                    int(usage.get("prompt_tokens") or usage.get("prompt_tokens_est") or 0)
                    + int(usage.get("completion_tokens") or 0)
                )
                or 0
            )
        if toks > 0:
            check_tenant_llm_budget(tid, add_tokens=toks, add_usd=0.0)
    except Exception:
        logger.debug("llm budget counter update skipped", exc_info=True)

    return receipt


def charge_from_agent_state(
    state: Any,
    usage: dict[str, Any] | None,
    *,
    step: int = 0,
    call_index: int = 0,
    provider: str = "",
    model_id: str = "",
) -> Optional[dict[str, Any]]:
    """Convenience: resolve tenant from AgentState.metadata and charge."""
    meta = getattr(state, "metadata", None) or {}
    if not isinstance(meta, dict):
        meta = {}
    user_id = meta.get("user_id") or 0
    tid = str(meta.get("tenant_id") or "").strip() or tenant_id_from_user(user_id)
    state_id = str(
        meta.get("state_id")
        or meta.get("run_id")
        or getattr(state, "work_dir", "")
        or ""
    )
    try:
        receipt = charge_llm_step(
            tid,
            usage,
            state_id=state_id,
            step=step,
            call_index=call_index,
            provider=provider or str((usage or {}).get("provider") or ""),
            model_id=model_id or str((usage or {}).get("model_id") or ""),
        )
    except InsufficientCreditsError:
        raise
    except Exception as exc:
        # Never let metering bugs kill a paid run silently as success —
        # log and re-raise only for insufficient; other errors are soft.
        logger.exception("live llm charge unexpected error: %s", type(exc).__name__)
        return {"charged": False, "skipped": True, "reason": f"charge_error:{type(exc).__name__}"}

    # Accumulate charge audit on state
    try:
        charges = list(meta.get("llm_charges") or [])
        charges.append(receipt)
        meta["llm_charges"] = charges[-50:]  # bound memory
        meta["llm_credits_charged"] = int(meta.get("llm_credits_charged") or 0) + int(
            receipt.get("credits") or 0
        )
        if hasattr(state, "metadata"):
            state.metadata = meta
    except Exception:
        pass
    return receipt


__all__ = [
    "InsufficientCreditsError",
    "live_charge_enabled",
    "tenant_id_from_user",
    "credits_for_llm_usage",
    "charge_llm_step",
    "charge_from_agent_state",
]
