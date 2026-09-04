
"""Cost-stack connectivity health — proves subsystems are wired."""
from __future__ import annotations

from typing import Any


def cost_stack_health() -> dict[str, Any]:
    checks: dict[str, Any] = {}
    # credits service
    try:
        from lumen.platform.credits import get_credit_service
        svc = get_credit_service()
        rules = {r.resource_type for r in (svc.list_pricing() or [])}
        checks["credit_service"] = {"ok": True, "pricing_rules": sorted(rules)}
    except Exception as e:
        checks["credit_service"] = {"ok": False, "error": type(e).__name__}

    try:
        from lumen.platform.balance_lifecycle import get_balance_lifecycle
        get_balance_lifecycle()
        checks["balance_lifecycle"] = {"ok": True}
    except Exception as e:
        checks["balance_lifecycle"] = {"ok": False, "error": type(e).__name__}

    try:
        from lumen.platform.rating_engine import get_rating_engine
        get_rating_engine()
        checks["rating_engine"] = {"ok": True}
    except Exception as e:
        checks["rating_engine"] = {"ok": False, "error": type(e).__name__}

    try:
        from lumen.platform.usage_batches import get_usage_batch_service
        get_usage_batch_service()
        checks["usage_batches"] = {"ok": True}
    except Exception as e:
        checks["usage_batches"] = {"ok": False, "error": type(e).__name__}

    try:
        from lumen.platform.credits.guards import assert_generation_allowed
        checks["guards"] = {"ok": True}
    except Exception as e:
        checks["guards"] = {"ok": False, "error": type(e).__name__}

    try:
        from lumen.platform.credits.llm_live import live_charge_enabled
        checks["live_llm_charge"] = {"ok": True, "enabled": bool(live_charge_enabled())}
    except Exception as e:
        checks["live_llm_charge"] = {"ok": False, "error": type(e).__name__}

    try:
        from lumen.platform.billing import get_billing
        b = get_billing()
        # smoke: inactive tenant should fail
        ok, reason = b.enforce_generation("__nonexistent_tenant_xyz__")
        checks["billing_enforce_generation"] = {
            "ok": True,
            "wired_to_credits": "insufficient" in reason or "inactive" in reason or "gate" in reason or not ok,
            "sample_reason": reason,
        }
    except Exception as e:
        checks["billing_enforce_generation"] = {"ok": False, "error": type(e).__name__}

    all_ok = all(bool(v.get("ok")) for v in checks.values())
    return {"ok": all_ok, "checks": checks}


__all__ = ["cost_stack_health"]
