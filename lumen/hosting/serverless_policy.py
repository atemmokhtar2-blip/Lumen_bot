"""Phase 4 — plan policy for Lumen serverless host (free vs pro).

Strict concurrent caps; no vendor names in user-facing strings.
Firecracker permanent path remains independent.
"""
from __future__ import annotations

import logging
import os
from typing import Any

logger = logging.getLogger("lumen.hosting.serverless_policy")


def is_serverless_backend_request() -> bool:
    hb = (os.environ.get("TBE_HOST_BACKEND") or "").strip().lower()
    return hb in {"lumen_serverless", "serverless", "vercel"}


def _free_serverless_cap() -> int:
    try:
        return max(0, int((os.environ.get("TBE_SERVERLESS_MAX_FREE") or "1").strip()))
    except ValueError:
        return 1


def _pro_serverless_cap() -> int:
    try:
        return max(1, int((os.environ.get("TBE_SERVERLESS_MAX_PRO") or "10").strip()))
    except ValueError:
        return 10


def max_serverless_bots(user_id: int) -> int:
    """Max concurrent lumen_serverless instances for this user."""
    try:
        from lumen.platform.entitlement import resolve_plan_limits

        limits = resolve_plan_limits(int(user_id or 0))
        if limits.is_pro:
            return max(1, min(int(limits.max_bots), _pro_serverless_cap()))
        return max(0, min(int(limits.max_bots), _free_serverless_cap()))
    except Exception as exc:
        logger.warning("max_serverless_bots fallback: %s", type(exc).__name__)
        # Env-only fallback when entitlement plane unavailable
        flag = (os.environ.get("TBE_USER_IS_PRO") or "").strip().lower()
        if flag in {"1", "true", "yes", "on"}:
            return _pro_serverless_cap()
        return _free_serverless_cap()


def count_serverless_running(instances: list[Any], *, user_id: int) -> int:
    n = 0
    for inst in instances:
        try:
            if int(getattr(inst, "user_id", 0) or 0) != int(user_id):
                continue
            if str(getattr(inst, "sandbox_backend", "") or "") != "lumen_serverless":
                continue
            if str(getattr(inst, "status", "") or "").lower() in {"running", "starting", "deploying"}:
                n += 1
        except Exception:
            continue
    return n


def assert_serverless_quota(*, user_id: int, running_serverless: int) -> tuple[bool, str]:
    cap = max_serverless_bots(int(user_id or 0))
    if cap <= 0:
        return False, "استضافة Lumen السريعة غير متاحة على خطتك الحالية."
    if running_serverless >= cap:
        return False, f"وصلت لحد الاستضافة السريعة ({running_serverless}/{cap}). أوقف بوتًا أو رقِّ خطتك."
    return True, "ok"


def status_message_ar(lifecycle_state: str, *, verify_ok: bool | None = None, raw: str = "") -> str:
    st = (lifecycle_state or "").upper()
    if st == "RUNNING" or verify_ok is True:
        return "البوت يعمل على استضافة Lumen وتم التحقق منه."
    if st == "FAILED":
        return (raw or "فشل تفعيل الاستضافة. أعد المحاولة أو استخدم الإصلاح.").strip()[:400]
    if st in {"DEPLOYED", "HEALTH_CHECK", "REGISTER_WEBHOOK", "VERIFY_WEBHOOK"}:
        return "جاري تفعيل البوت على استضافة Lumen…"
    return (raw or "حالة الاستضافة قيد التحديث.").strip()[:400]


__all__ = [
    "is_serverless_backend_request",
    "max_serverless_bots",
    "count_serverless_running",
    "assert_serverless_quota",
    "status_message_ar",
]
