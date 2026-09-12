"""Phase 2: template reserve side-effects (no hosting start yet).

Calls TemplateService.reserve only — host pipeline is Phase 3–4.
"""
from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger("lumen_bot.ui.callbacks.templates")


async def execute_template_reserve(
    *,
    effect: str,
    user_id: int,
    user_data: dict[str, Any] | None,
) -> str:
    """Returns Arabic note for the user (empty if nothing to add)."""
    ud = user_data if isinstance(user_data, dict) else {}
    # slots may live on engine_ui_state
    slots: dict[str, Any] = {}
    st = ud.get("engine_ui") or ud.get("engine_ui_state") or ud.get("ui_state") or {}
    if isinstance(st, dict):
        slots = dict(st.get("slots") or {})
    tid = str(slots.get("template_id") or ud.get("template_id") or "").strip()
    if not tid:
        return "تعذر تحديد القالب."

    try:
        from lumen.templates.service import TemplateService
        from lumen.templates.models import TemplateLaunchMode

        svc = TemplateService()
        if effect == "tpl_reserve_trial":
            try:
                mins = int(slots.get("trial_minutes") or 0)
            except (TypeError, ValueError):
                mins = 0
            res = svc.reserve(
                int(user_id),
                template_id=tid,
                mode=TemplateLaunchMode.TRIAL,
                trial_minutes=mins,
            )
            if not res.ok:
                return _deny_ar(res.reason)
            inst = res.instance
            assert inst is not None
            ud["last_template_instance_id"] = inst.instance_id
            return (
                f"✅ تم حجز تجربة القالب «{tid}» لمدة {inst.trial_minutes} دقيقة "
                f"(ينتهي تلقائيًا). التشغيل على الاستضافة في خطوة لاحقة."
            )
        if effect == "tpl_reserve_permanent":
            res = svc.reserve(
                int(user_id),
                template_id=tid,
                mode=TemplateLaunchMode.PERMANENT,
            )
            if not res.ok:
                return _deny_ar(res.reason)
            inst = res.instance
            assert inst is not None
            ud["last_template_instance_id"] = inst.instance_id
            return (
                f"✅ تم حجز استخدام دائم للقالب «{tid}» لمدة 30 يومًا "
                f"(حد 3 قوالب شغّالة في المجاني). التشغيل على الاستضافة لاحقًا."
            )
    except Exception:
        logger.exception("template reserve failed effect=%s uid=%s", effect, user_id)
        return "تعذر حجز القالب حاليًا."
    return ""


def _deny_ar(reason: str) -> str:
    r = reason or ""
    if "max_running" in r:
        return "وصلت لحد 3 قوالب شغّالة في الخطة المجانية. أوقف أحدها أولًا."
    if "trial_minutes" in r:
        return "مدة التجربة يجب أن تكون بين 1 و 50 دقيقة."
    if "template_not_found" in r:
        return "القالب غير موجود."
    return f"تعذر الحجز ({r})."


__all__ = ["execute_template_reserve"]
