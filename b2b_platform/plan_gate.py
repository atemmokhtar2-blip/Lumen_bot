"""Server-side plan gates for consumer bot + API (no client trust)."""
from __future__ import annotations

import logging
import os
from typing import Any

logger = logging.getLogger(__name__)


def _mongo_enabled() -> bool:
    return bool((os.getenv("MONGODB_URI") or "").strip())


def resolve_user_plan(user_id: int | None = None, tenant_id: str | None = None) -> str:
    """Return canonical plan id for a Telegram user or tenant."""
    try:
        from .plans import normalize_plan_id, get_plan
        from .tenants import get_tenant_store
        store = get_tenant_store()
        if tenant_id:
            t = store.get(tenant_id)
            if t:
                return normalize_plan_id(t.plan_id)
        if user_id and hasattr(store, "get_by_telegram"):
            t = store.get_by_telegram(int(user_id))
            if t:
                return normalize_plan_id(t.plan_id)
    except Exception as exc:
        logger.debug("resolve_user_plan fallback: %s", type(exc).__name__)
    return "explorer"


def check_generation_quota(user_id: int | None = None, tenant_id: str | None = None) -> tuple[bool, str, dict[str, Any]]:
    """Atomic generation quota check. Returns (ok, reason, info)."""
    from .plans import get_plan, normalize_plan_id
    from .tenants import get_tenant_store
    from .billing import get_billing

    store = get_tenant_store()
    tid = tenant_id
    if not tid and user_id and hasattr(store, "get_by_telegram"):
        t = store.get_by_telegram(int(user_id))
        if t:
            tid = t.tenant_id
    if not tid:
        # No identity yet — allow only if no mongo (dev); else require user record
        if not _mongo_enabled():
            plan = get_plan("explorer")
            return True, "ok_dev_no_tenant", {"plan_id": "explorer", "limit": plan.generations_per_month}
        return False, "user_not_registered", {"plan_id": "explorer"}

    ok, reason = get_billing().enforce_generation(tid, reserve=True)
    t = store.get(tid)
    plan = get_plan(t.plan_id if t else "explorer")
    info = {
        "tenant_id": tid,
        "plan_id": plan.id,
        "limit": plan.generations_per_month,
        "reason": reason,
    }
    return ok, reason, info


def live_seconds_for_user(user_id: int | None = None, tenant_id: str | None = None) -> int:
    from .plans import get_plan
    plan = get_plan(resolve_user_plan(user_id, tenant_id))
    return int(plan.live_preview_seconds)


def apply_post_generation(project_path: str, user_id: int | None = None, tenant_id: str | None = None) -> dict[str, Any]:
    """Watermark + engine notes after a successful generate."""
    from .plans import get_plan
    plan = get_plan(resolve_user_plan(user_id, tenant_id))
    out: dict[str, Any] = {"plan_id": plan.id, "watermark": False}
    if plan.watermark and project_path:
        try:
            from .watermark import inject_watermark
            out["watermark"] = bool(inject_watermark(project_path))
        except Exception as exc:
            logger.warning("post_gen watermark: %s", type(exc).__name__)
    return out


def filter_preferred_keys(keys: list | None, user_id: int | None = None, tenant_id: str | None = None) -> list:
    from .plans import filter_engines_for_plan
    return filter_engines_for_plan(resolve_user_plan(user_id, tenant_id), list(keys or []))
