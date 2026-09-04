"""Build live, user-scoped context for the conversational model.

This module is deliberately read-only. It never accepts plan or usage values from
Telegram input and never invents quota numbers when the user cannot be resolved.
"""
from __future__ import annotations

from typing import Any

from lumen.platform.metering import get_metering
from lumen.platform.plans import get_plan, public_plan_dict
from lumen.platform.tenants import get_tenant_store


def _remaining(limit: int, used: int) -> int | None:
    # A zero quota means unlimited in the plan contract; None is clearer than 0.
    if int(limit or 0) <= 0:
        return None
    return max(0, int(limit) - int(used or 0))


def build_live_user_context(telegram_user_id: int) -> dict[str, Any]:
    """Return only current server-side facts for one Telegram user."""
    uid = int(telegram_user_id or 0)
    store = get_tenant_store()
    tenant = store.get_by_telegram(uid) if uid else None
    if tenant is None:
        return {
            "identity_known": False,
            "telegram_user_id": uid,
            "data_available": False,
            "reason": "user_not_resolved",
        }

    plan = get_plan(getattr(tenant, "plan_id", "free"))
    usage = get_metering().snapshot(str(tenant.tenant_id))
    plan_payload = public_plan_dict(plan)
    payload: dict[str, Any] = {
        "identity_known": True,
        "data_available": True,
        "tenant_id": str(tenant.tenant_id),
        "telegram_user_id": uid,
        "account": {
            "name": str(getattr(tenant, "name", "") or ""),
            "active": bool(getattr(tenant, "active", True)),
        },
        "plan": plan_payload,
        "usage": {
            "period": usage.get("period"),
            "generations_used": int(usage.get("generations", 0) or 0),
            "messages_used": int(usage.get("messages", 0) or 0),
            "characters_used": int(usage.get("characters", 0) or 0),
            "api_calls_used": int(usage.get("api_calls", 0) or 0),
            "host_starts_used": int(usage.get("host_starts", 0) or 0),
        },
        "remaining": {
            "generations": _remaining(plan.generations_per_month, usage.get("generations", 0)),
            "messages": _remaining(plan.messages_per_month, usage.get("messages", 0)),
            "characters": None,
            "hosted_bots": _remaining(plan.hosted_bots, usage.get("host_starts", 0)),
        },
        "source": "server_live_plan_and_metering",
    }
    # Active multi-conversation thread (WhatsApp-style sliding window)
    try:
        from lumen.platform.conversations import get_conversation_service

        svc = get_conversation_service()
        rows = svc.list_for_user(uid, limit=1)
        if rows:
            ctx = svc.context_for_llm(uid, rows[0].id)
            payload["conversation"] = {
                "id": ctx.get("conversation_id"),
                "title": ctx.get("title"),
                "summary": (ctx.get("summary") or "")[:500],
                "recent": (ctx.get("messages") or [])[-10:],
            }
    except Exception:
        pass
    return payload
