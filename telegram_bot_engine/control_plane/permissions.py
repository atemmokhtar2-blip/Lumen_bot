"""Permissions — who may generate / use cline / deploy (control plane)."""
from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any


@dataclass
class PermissionDecision:
    allowed: bool
    reason: str
    limits: dict[str, Any]


def check_generate_permission(
    user_id: int,
    *,
    engine_mode: str = "catalog",
) -> PermissionDecision:
    """Default public product: allow all. Ops can lock via env."""
    lock = (os.getenv("LOCK_BOT_TO_ALLOWLIST") or "0").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }
    if lock:
        raw = (os.getenv("ALLOWED_USER_IDS") or "").strip()
        allowed_ids = {int(x) for x in raw.split(",") if x.strip().isdigit()}
        if int(user_id or 0) not in allowed_ids:
            return PermissionDecision(
                False,
                "user_not_on_allowlist",
                {"allowlist_size": len(allowed_ids)},
            )

    if engine_mode == "cline":
        if (os.getenv("CLINE_ENABLED") or "0").strip().lower() not in {
            "1",
            "true",
            "yes",
            "on",
        }:
            # Still allowed — runtime falls back to catalog
            return PermissionDecision(
                True,
                "cline_disabled_will_fallback_catalog",
                {"engine_mode": engine_mode},
            )

    return PermissionDecision(True, "ok", {"engine_mode": engine_mode})


__all__ = ["PermissionDecision", "check_generate_permission"]
