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

import contextvars
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

# Bound per agent step so decide() / _record_usage can charge without plumbing
# tenant_id through every provider call.
_CHARGE_CTX: contextvars.ContextVar[dict[str, Any] | None] = contextvars.ContextVar(
    "lumen_llm_charge_ctx", default=None
)


def bind_charge_context(
    *,
    tenant_id: str = "",
    user_id: int = 0,
    state_id: str = "",
    step: int = 0,
    call_index: int = 0,
) -> contextvars.Token:
    """Bind charging context for the current agent step (call from agent_loop)."""
    tid = str(tenant_id or "").strip() or tenant_id_from_user(user_id)
    ctx = {
        "tenant_id": tid,
        "user_id": int(user_id or 0),
        "state_id": str(state_id or ""),
        "step": int(step or 0),
        "call_index": int(call_index or 0),
    }
    return _CHARGE_CTX.set(ctx)


def clear_charge_context(token: contextvars.Token | None = None) -> None:
    try:
        if token is not None:
            _CHARGE_CTX.reset(token)
        else:
            _CHARGE_CTX.set(None)
    except Exception:
        try:
            _CHARGE_CTX.set(None)
        except Exception:
            pass


def get_charge_context() -> dict[str, Any] | None:
    try:
        ctx = _CHARGE_CTX.get()
        return dict(ctx) if isinstance(ctx, dict) else None
    except Exception:
        return None


def charge_bound_usage(
    usage: dict[str, Any] | None,
    *,
    provider: str = "",
    model_id: str = "",
    credit_service: Any = None,
) -> dict[str, Any] | None:
    """Charge using the bound context. Raises InsufficientCreditsError on fail.

    Returns receipt or None when no context / skipped.
    """
    ctx = get_charge_context()
    if not ctx:
        return None
    tid = str(ctx.get("tenant_id") or "")
    if not tid:
        return None
    # bump call_index in context for multi-attempt decide retries
    call_index = int(ctx.get("call_index") or 0) + 1
    ctx["call_index"] = call_index
    try:
        _CHARGE_CTX.set(ctx)
    except Exception:
        pass
    return charge_llm_step(
        tid,
        usage,
        state_id=str(ctx.get("state_id") or ""),
        step=int(ctx.get("step") or 0),
        call_index=call_index,
        provider=provider,
        model_id=model_id,
        credit_service=credit_service,
    )


def credits_for_llm_usage(usage: dict[str, Any] | None, *, credit_service: Any = None) -> int:
    """Convert provider usage → integer credits based on **actual model cost**.

    NOT a fixed generation fee. Formula:

      USD = estimate_cost_usd(usage)   # model-aware $/1M rates for provider+model
      credits = ceil(USD * LUMEN_CREDITS_PER_USD)   # default 1000 credits per $1

    Optional: if LUMEN_LLM_FLAT_1K_PRICING=1, fall back to llm_prompt_1k /
    llm_completion_1k rules (legacy flat path).

    Floor: any real token traffic → at least 1 credit (except pure-local $0 models
    when LUMEN_LOCAL_LLM_FREE=1).
    """
    u = dict(usage or {})
    prompt = int(u.get("prompt_tokens") or u.get("prompt_tokens_est") or 0)
    completion = int(u.get("completion_tokens") or 0)
    if prompt <= 0 and completion <= 0:
        total = int(u.get("total_tokens") or 0)
        if total <= 0:
            return 0
        prompt = int(total * 0.7)
        completion = max(0, total - prompt)

    flat = (os.getenv("LUMEN_LLM_FLAT_1K_PRICING") or "0").strip().lower() in {
        "1", "true", "yes", "on",
    }
    if flat and credit_service is None:
        try:
            from lumen.platform.credits import get_credit_service

            credit_service = get_credit_service()
        except Exception:
            credit_service = None
    if flat and credit_service is not None:
        try:
            p_units = (prompt + 999) // 1000 if prompt > 0 else 0
            c_units = (completion + 999) // 1000 if completion > 0 else 0
            p_cost = int(credit_service.cost_for("llm_prompt_1k", p_units)) if p_units else 0
            c_cost = int(credit_service.cost_for("llm_completion_1k", c_units)) if c_units else 0
            rules = {r.resource_type for r in (credit_service.list_pricing() or [])}
            if "llm_prompt_1k" in rules or "llm_completion_1k" in rules:
                credits = p_cost + c_cost
                if credits <= 0 and (prompt > 0 or completion > 0):
                    credits = 1
                return max(0, int(credits))
        except Exception:
            logger.debug("flat 1k pricing path failed", exc_info=True)

    # Primary path: model-aware USD → credits
    try:
        from lumen.engine.services.evaluation.cost_model import estimate_cost_usd

        usd = float(estimate_cost_usd(u) or 0.0)
    except Exception:
        usd = 0.0
    try:
        # 1000 credits per $1 → $0.001 = 1 credit (fine-grained metering)
        rate = float(os.getenv("LUMEN_CREDITS_PER_USD") or "1000")
    except ValueError:
        rate = 1000.0
    rate = max(0.0, rate)
    credits = int(math.ceil(usd * rate)) if usd > 0 and rate > 0 else 0

    local_free = (os.getenv("LUMEN_LOCAL_LLM_FREE") or "0").strip().lower() in {
        "1", "true", "yes", "on",
    }
    prov = str(u.get("provider") or "").lower()
    if credits <= 0 and (prompt > 0 or completion > 0):
        if local_free and prov in {"ollama", "llamacpp"}:
            return 0
        credits = 1  # floor for any cloud traffic
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

    # Ensure model identity is on the usage dict for model-aware USD pricing
    usage_m = dict(usage or {})
    if provider and not usage_m.get("provider"):
        usage_m["provider"] = provider
    if model_id and not usage_m.get("model_id"):
        usage_m["model_id"] = model_id

    amount = credits_for_llm_usage(usage_m, credit_service=credit_service)
    receipt["credits"] = amount
    if amount <= 0:
        receipt["skipped"] = True
        receipt["reason"] = "zero_usage"
        return receipt

    # Hard daily spend cap (env LUMEN_DAILY_CREDIT_CAP, 0 = unlimited)
    try:
        daily_cap = int(os.getenv("LUMEN_DAILY_CREDIT_CAP") or "0")
    except ValueError:
        daily_cap = 0
    if daily_cap > 0:
        try:
            spent_today = _tenant_llm_spent_today(tid, credit_service)
            if spent_today + amount > daily_cap:
                raise InsufficientCreditsError(
                    tenant_id=tid,
                    needed=amount,
                    available=max(0, daily_cap - spent_today),
                    step=int(step or 0),
                    reason="daily_credit_cap",
                )
        except InsufficientCreditsError:
            raise
        except Exception:
            logger.debug("daily cap check soft-fail", exc_info=True)

    if credit_service is None:
        from lumen.platform.credits import get_credit_service

        credit_service = get_credit_service()

    sid = str(state_id or "").strip() or "nostate"
    idem = f"llm:{tid}:{sid}:{int(step)}:{int(call_index)}"
    # Keep key within typical store limits
    if len(idem) > 180:
        idem = idem[:180]

    meta = {
        "provider": str(provider or usage_m.get("provider") or ""),
        "model_id": str(model_id or usage_m.get("model_id") or ""),
        "step": int(step or 0),
        "call_index": int(call_index or 0),
        "usage": {
            k: usage_m.get(k)
            for k in (
                "prompt_tokens",
                "completion_tokens",
                "total_tokens",
                "prompt_tokens_est",
                "estimated",
                "provider",
                "model_id",
            )
            if usage_m.get(k) is not None
        },
        "usd_estimate": None,
    }
    try:
        from lumen.engine.services.evaluation.cost_model import estimate_cost_usd
        meta["usd_estimate"] = float(estimate_cost_usd(usage_m) or 0.0)
    except Exception:
        pass

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




def usage_from_provider_body(
    body: dict | None,
    *,
    provider: str = "",
    model_id: str = "",
    prompt_chars: int = 0,
) -> dict[str, Any]:
    """Normalize provider JSON → usage dict for model-aware metering."""
    body = body or {}
    usage: dict[str, Any] = {"provider": provider or "", "model_id": model_id or ""}
    um = body.get("usageMetadata") or body.get("usage_metadata") or {}
    if um:
        usage["prompt_tokens"] = int(um.get("promptTokenCount") or um.get("prompt_tokens") or 0)
        usage["completion_tokens"] = int(um.get("candidatesTokenCount") or um.get("completion_tokens") or 0)
        usage["total_tokens"] = int(um.get("totalTokenCount") or um.get("total_tokens") or 0)
    ou = body.get("usage") or {}
    if ou and not usage.get("total_tokens"):
        usage["prompt_tokens"] = int(ou.get("prompt_tokens") or ou.get("input_tokens") or 0)
        usage["completion_tokens"] = int(ou.get("completion_tokens") or ou.get("output_tokens") or 0)
        usage["total_tokens"] = int(ou.get("total_tokens") or 0)
        if not usage["total_tokens"]:
            usage["total_tokens"] = int(usage["prompt_tokens"]) + int(usage["completion_tokens"])
    if not usage.get("total_tokens") and prompt_chars:
        usage["prompt_tokens_est"] = max(1, int(prompt_chars) // 4)
        usage["estimated"] = True
    return usage


def meter_http_response(
    body: dict | None,
    *,
    provider: str,
    model_id: str = "",
    prompt_chars: int = 0,
    tenant_id: str = "",
    user_id: int = 0,
    state_id: str = "",
    step: int = 0,
    credit_service: Any = None,
) -> dict[str, Any] | None:
    """Meter any direct HTTP LLM call (repo explain, extraction, etc.).

    Prefer bound charge context; else tenant_id / user_id.
    Raises InsufficientCreditsError on insufficient balance.
    """
    usage = usage_from_provider_body(
        body, provider=provider, model_id=model_id, prompt_chars=prompt_chars
    )
    ctx = get_charge_context()
    if ctx:
        return charge_bound_usage(
            usage,
            provider=provider,
            model_id=model_id,
            credit_service=credit_service,
        )
    tid = str(tenant_id or "").strip()
    if not tid and user_id:
        tid = tenant_id_from_user(user_id)
    if not tid:
        # No tenant → cannot bill; log for ops (do not silently ignore in metrics)
        logger.warning("meter_http_response skipped: no tenant provider=%s model=%s", provider, model_id)
        return {"charged": False, "skipped": True, "reason": "no_tenant", "usage": usage}
    return charge_llm_step(
        tid,
        usage,
        state_id=state_id or f"direct:{provider}",
        step=int(step or 0),
        call_index=1,
        provider=provider,
        model_id=model_id,
        credit_service=credit_service,
    )


def enqueue_pending_llm_charge(payload: dict[str, Any]) -> None:
    """Idempotent residual queue for charges that could not complete (ops scheduler)."""
    try:
        from pathlib import Path
        import json
        import time

        root = Path(os.getenv("LUMEN_PENDING_LLM_DIR") or "/tmp/lumen_pending_llm")
        root.mkdir(parents=True, exist_ok=True)
        key = str(payload.get("idempotency_key") or "").strip()
        if not key or len(key) < 8:
            key = f"pending:{int(time.time()*1000)}"
        safe = "".join(c if c.isalnum() or c in "-_." else "_" for c in key)[:120]
        path = root / f"{safe}.json"
        if path.exists():
            return
        path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    except Exception:
        logger.debug("enqueue_pending_llm_charge failed", exc_info=True)


def flush_pending_llm_charges(*, limit: int = 50, credit_service: Any = None) -> dict[str, int]:
    """Process residual LLM charge files (idempotent). Called from ops scheduler."""
    stats = {"seen": 0, "charged": 0, "failed": 0, "skipped": 0}
    try:
        from pathlib import Path
        import json

        root = Path(os.getenv("LUMEN_PENDING_LLM_DIR") or "/tmp/lumen_pending_llm")
        if not root.is_dir():
            return stats
        files = sorted(root.glob("*.json"))[: max(1, int(limit))]
        for path in files:
            stats["seen"] += 1
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except Exception:
                stats["failed"] += 1
                continue
            tid = str(payload.get("tenant_id") or "")
            usage = payload.get("usage") if isinstance(payload.get("usage"), dict) else {}
            if not tid or not usage:
                stats["skipped"] += 1
                try:
                    path.unlink(missing_ok=True)
                except Exception:
                    pass
                continue
            try:
                receipt = charge_llm_step(
                    tid,
                    usage,
                    state_id=str(payload.get("state_id") or "pending"),
                    step=int(payload.get("step") or 0),
                    call_index=int(payload.get("call_index") or 1),
                    provider=str(payload.get("provider") or usage.get("provider") or ""),
                    model_id=str(payload.get("model_id") or usage.get("model_id") or ""),
                    credit_service=credit_service,
                )
                if receipt.get("charged") or receipt.get("skipped"):
                    stats["charged"] += 1
                    try:
                        path.unlink(missing_ok=True)
                    except Exception:
                        pass
            except InsufficientCreditsError:
                stats["failed"] += 1
                # keep file for retry after top-up
            except Exception:
                stats["failed"] += 1
                logger.debug("flush pending llm failed", exc_info=True)
    except Exception:
        logger.debug("flush_pending_llm_charges error", exc_info=True)
    return stats


__all__ = [
    "InsufficientCreditsError",
    "live_charge_enabled",
    "tenant_id_from_user",
    "credits_for_llm_usage",
    "charge_llm_step",
    "meter_http_response",
    "usage_from_provider_body",
    "flush_pending_llm_charges",
    "enqueue_pending_llm_charge",
    "charge_from_agent_state",
    "bind_charge_context",
    "clear_charge_context",
    "get_charge_context",
    "charge_bound_usage",
]
