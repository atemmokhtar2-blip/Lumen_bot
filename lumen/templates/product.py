"""Product polish helpers for the templates plane (Phase 6)."""
from __future__ import annotations

import logging

from lumen.templates.policy import FREE_MAX_RUNNING

logger = logging.getLogger(__name__)

# Pro may run more concurrent template bots than free tier.
PRO_MAX_RUNNING = 10

_STATUS_AR = {
    "preparing": "قيد التجهيز",
    "running": "شغّال",
    "stopped": "متوقف",
    "expired": "منتهٍ",
    "failed": "فشل",
}
_MODE_AR = {
    "trial": "تجربة مؤقتة",
    "permanent": "استخدام دائم",
}


def status_label_ar(status: str) -> str:
    s = (status or "").strip().lower()
    return _STATUS_AR.get(s, status or "—")


def mode_label_ar(mode: str) -> str:
    m = (mode or "").strip().lower()
    return _MODE_AR.get(m, mode or "—")


def resolve_max_template_slots(user_id: int) -> int:
    """Free = 3; active Lumen Pro = PRO_MAX_RUNNING. Fail-closed to free."""
    uid = int(user_id or 0)
    if uid <= 0:
        return FREE_MAX_RUNNING
    try:
        from lumen.platform.entitlement import resolve_pro_entitlement

        if resolve_pro_entitlement(uid) is not None:
            return max(FREE_MAX_RUNNING, int(PRO_MAX_RUNNING))
    except Exception:
        logger.debug("template slot entitlement resolve soft-fail", exc_info=True)
    return FREE_MAX_RUNNING


def quota_footer_ar(user_id: int, *, active: int | None = None) -> str:
    cap = resolve_max_template_slots(user_id)
    if active is None:
        return f"الحد: {cap} قوالب شغّالة" + (" (Pro)" if cap > FREE_MAX_RUNNING else " (مجاني)")
    return f"المستخدم: {active}/{cap}" + (" — Pro" if cap > FREE_MAX_RUNNING else " — مجاني")


__all__ = [
    "PRO_MAX_RUNNING",
    "status_label_ar",
    "mode_label_ar",
    "resolve_max_template_slots",
    "quota_footer_ar",
]
