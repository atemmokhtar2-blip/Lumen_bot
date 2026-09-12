"""Template plane side-effects — Phase 2 reserve + Phase 3 trial binding.

Phase 3: materialize assets → pending_run (TRIAL_CHAT) → secret prompt.
Does not start LiveRunner itself; token_handler + live.py own the start.
"""
from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger("lumen_bot.ui.callbacks.templates")


def _slots_from_ud(ud: dict[str, Any]) -> dict[str, Any]:
    st = ud.get("engine_ui") or ud.get("engine_ui_state") or ud.get("ui_state") or {}
    if isinstance(st, dict):
        return dict(st.get("slots") or {})
    return {}


def _deny_ar(reason: str) -> str:
    r = reason or ""
    if "max_running" in r:
        return "وصلت لحد 3 قوالب شغّالة في الخطة المجانية. أوقف أحدها أولًا."
    if "trial_minutes" in r:
        return "مدة التجربة يجب أن تكون بين 1 و 50 دقيقة."
    if "template_not_found" in r:
        return "القالب غير موجود."
    if "materialize" in r or "asset" in r:
        return "تعذر تجهيز ملفات القالب على الخادم."
    return f"تعذر الحجز ({r})."


async def execute_template_reserve(
    *,
    effect: str,
    user_id: int,
    user_data: dict[str, Any] | None,
    message=None,
) -> str:
    """Reserve quota + for trial: materialize project and bind TRIAL_CHAT plane."""
    ud = user_data if isinstance(user_data, dict) else {}
    slots = _slots_from_ud(ud)
    tid = str(slots.get("template_id") or ud.get("template_id") or "").strip()
    if not tid:
        return "تعذر تحديد القالب."

    try:
        from lumen.templates.service import TemplateService
        from lumen.templates.models import TemplateLaunchMode, TemplateInstanceStatus

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
            if not res.ok or res.instance is None:
                return _deny_ar(res.reason)
            inst = res.instance
            try:
                from lumen.templates.materialize import materialize_to_sandbox

                root = materialize_to_sandbox(int(user_id), inst.template_id)
            except Exception as exc:
                logger.exception("template materialize failed")
                try:
                    svc.mark_stopped(int(user_id), inst.instance_id)
                except Exception:
                    pass
                return _deny_ar(f"materialize:{type(exc).__name__}")

            seconds = max(60, int(inst.trial_minutes or mins or 1) * 60)
            seconds = min(seconds, 50 * 60)

            from lumen.engine.services.runtime_planes import RuntimePlane, plane_label_ar
            from lumen.bot.ui.project_resolve import bind_active_repo, resolve_entry_point

            entry = resolve_entry_point(root) or "main.py"
            payload = {
                "project_path": str(root),
                "owner_user_id": int(user_id) or None,
                "entry_point": entry,
                "run_seconds": seconds,
                "sandbox": True,
                "plane": RuntimePlane.TRIAL_CHAT.value,
                "template_id": inst.template_id,
                "template_instance_id": inst.instance_id,
                "source": "template",
            }
            ud["pending_run"] = dict(payload)
            ud["pending_live_run"] = dict(payload)
            ud["pending_deploy"] = dict(payload)
            ud.pop("pending_host", None)
            ud["last_template_instance_id"] = inst.instance_id
            bind_active_repo(ud, root, entry=entry)

            try:
                meta = dict(inst.meta or {})
                meta["project_path"] = str(root)
                meta["run_seconds"] = seconds
                svc._patch(  # noqa: SLF001
                    int(user_id),
                    inst.instance_id,
                    status=TemplateInstanceStatus.PREPARING,
                    meta=meta,
                )
            except Exception:
                logger.debug("template instance meta patch failed", exc_info=True)

            try:
                from lumen.bot.session_store import get_session_store

                if user_id:
                    get_session_store().save(int(user_id), dict(ud))
            except Exception:
                logger.debug("template session persist failed", exc_info=True)

            label = plane_label_ar(RuntimePlane.TRIAL_CHAT)
            body = (
                "تم تجهيز القالب "
                + str(inst.template_id)
                + "\n• "
                + label
                + "\n• المدة: "
                + str(seconds // 60)
                + " دقيقة (حد أقصى 50)\n• المشروع: `"
                + str(root)
                + "`\n• نقطة الدخول: `"
                + str(entry)
                + "`\n\nأرسل توكن البوت من @BotFather الآن لبدء التجربة."
            )
            if message is not None:
                try:
                    from lumen.bot.ui.secret_prompt import prompt_for_secret

                    await prompt_for_secret(
                        message=message, kind="bot", body=body, user_id=int(user_id or 0)
                    )
                    return ""
                except Exception:
                    logger.exception("template trial secret prompt failed")
            return body

        if effect == "tpl_reserve_permanent":
            res = svc.reserve(
                int(user_id),
                template_id=tid,
                mode=TemplateLaunchMode.PERMANENT,
            )
            if not res.ok or res.instance is None:
                return _deny_ar(res.reason)
            ud["last_template_instance_id"] = res.instance.instance_id
            return (
                "تم حجز استخدام دائم للقالب "
                + tid
                + " لمدة 30 يومًا (حد 3 قوالب). ربط الاستضافة الدائمة لاحقًا."
            )
    except Exception:
        logger.exception("template reserve failed effect=%s uid=%s", effect, user_id)
        return "تعذر حجز القالب حاليًا."
    return ""


__all__ = ["execute_template_reserve"]
