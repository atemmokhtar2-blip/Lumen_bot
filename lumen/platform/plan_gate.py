"""Plan gates REMOVED — credits-only platform.

All former plan checks return allow. Callers should migrate to CreditService.
"""
from __future__ import annotations

from typing import Any


def resolve_user_plan(user_id: int = 0, tenant_id: str | None = None) -> str:
    return "default"


def check_generation_allowed(
    user_id: int = 0,
    tenant_id: str | None = None,
    **_: Any,
) -> tuple[bool, str, dict[str, Any]]:
    return True, "ok", {"plan_id": "default", "limit": 0, "billing": "credits_only"}


def check_feature_allowed(
    feature: str,
    user_id: int = 0,
    tenant_id: str | None = None,
    **_: Any,
) -> tuple[bool, str]:
    return True, "ok"


def check_hosting_allowed(
    user_id: int = 0,
    tenant_id: str | None = None,
    current_hosted: int = 0,
    **_: Any,
) -> tuple[bool, str]:
    return True, "ok"


def engine_tier_for(user_id: int = 0, tenant_id: str | None = None) -> str:
    return "advanced"
