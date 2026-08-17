"""Live, read-only context for natural dialogue answers.

The dialogue model may interpret the question, but all numeric account facts come
from the current tenant, plan, metering bucket, and project manifest.
"""
from __future__ import annotations

from typing import Any

from b2b_platform.metering import get_metering
from b2b_platform.plans import get_plan, normalize_plan_id, public_plan_dict
from b2b_platform.tenants import get_tenant_store

from .project_context import project_manifest


def _tenant(sender_id: str):
    try:
        return get_tenant_store().get_by_telegram(int(sender_id))
    except (TypeError, ValueError, OSError):
        return None


def build_live_context(sender_id: str, fallback_plan_id: str | None = None) -> dict[str, Any]:
    tenant = _tenant(sender_id)
    plan_id = getattr(tenant, "plan_id", None) or fallback_plan_id or "free"
    plan_id = normalize_plan_id(plan_id)
    plan = public_plan_dict(get_plan(plan_id))
    tenant_id = str(getattr(tenant, "tenant_id", "") or getattr(tenant, "id", "") or "")
    usage = get_metering().snapshot(tenant_id) if tenant_id else {}

    def remaining(limit_key: str, used_key: str) -> int | None:
        limit = int(plan.get(limit_key) or 0)
        if limit <= 0:
            return None
        return max(0, limit - int(usage.get(used_key) or 0))

    manifest = project_manifest()
    return {
        "plan": plan,
        "usage": {
            "period": usage.get("period"),
            "generations_used": int(usage.get("generations") or 0),
            "generations_remaining": remaining("generations_per_month", "generations"),
            "messages_used": int(usage.get("messages") or 0),
            "messages_remaining": remaining("messages_per_month", "messages"),
            "characters_used": int(usage.get("characters") or 0),
        },
        "project": {
            "fingerprint": manifest.get("fingerprint", ""),
            "root": manifest.get("root", ""),
            "packages": manifest.get("packages", {}),
            "models": manifest.get("models", []),
            "plan_ids": manifest.get("plan_ids", []),
        },
        "tenant_id": tenant_id,
        "source": "live_runtime",
    }
