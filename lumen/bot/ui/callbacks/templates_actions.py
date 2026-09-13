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
        return "وصلت لحد القوالب الشغّالة (3 مجاني / حتى 10 لـ Pro). أوقف أحدها أولًا من «بوتاتي»."
    if "trial_minutes" in r:
        return "مدة التجربة يجب أن تكون بين 1 و 50 دقيقة."
    if "template_not_found" in r or "invalid_template" in r:
        return "القالب غير موجود أو غير مفعّل في الكتالوج."
    if "materialize" in r or "asset" in r:
        return "تعذر تجهيز ملفات القالب على الخادم."
    if "redis" in r.lower() or "store" in r.lower():
        return "تعذر حفظ الحجز مؤقتًا (تخزين القوالب). أعد المحاولة بعد ثوانٍ."
    if "reserve_contention" in r:
        return "الحجز متزامن — أعد المحاولة."
    return f"تعذر الحجز ({r[:120]})."


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

    if effect == "tpl_stop_instance":
        iid = str(slots.get("tpl_stop_target") or ud.get("tpl_stop_target") or "").strip()
        if not iid:
            return "لم يُحدد قالب للإيقاف."
        try:
            from lumen.templates.host_adapter import stop_user_instance, list_user_status

            ok, reason, host_id = stop_user_instance(int(user_id), iid)
            if not ok:
                return "تعذر الإيقاف (" + reason + ")."
            # Best-effort host stop outside templates package
            if host_id and not str(host_id).startswith("pid:"):
                try:
                    import os
                    from pathlib import Path as _P
                    from lumen.engine.services.hosting import get_hosting_service
                    from lumen.bot.helpers import OUTPUT_DIR  # type: ignore

                    get_hosting_service(OUTPUT_DIR).stop(
                        instance_id=str(host_id), user_id=int(user_id)
                    )
                except Exception:
                    logger.debug("host stop after template stop soft-fail", exc_info=True)
            # Refresh engine_ui status slots
            try:
                st = ud.get("engine_ui") if isinstance(ud.get("engine_ui"), dict) else {}
                slots2 = dict(st.get("slots") or {})
                for i in range(5):
                    slots2.pop(f"tpl_i{i}", None)
                    slots2.pop(f"tpl_s{i}", None)
                    slots2.pop(f"tpl_t{i}", None)
                    slots2.pop(f"tpl_r{i}", None)
                rows = list_user_status(int(user_id))[:5]
                for i, row in enumerate(rows):
                    slots2[f"tpl_i{i}"] = row.instance_id
                    slots2[f"tpl_s{i}"] = row.status
                    slots2[f"tpl_t{i}"] = row.title[:40]
                    slots2[f"tpl_r{i}"] = row.remaining_label_ar[:20]
                slots2.pop("tpl_stop_target", None)
                st = dict(st)
                st["slots"] = slots2
                st["phase"] = "template_status"
                ud["engine_ui"] = st
            except Exception:
                logger.debug("refresh template status slots failed", exc_info=True)
            return "تم إيقاف القالب وتحرير مقعد من الحصة (حد 3)."
        except Exception:
            logger.exception("tpl_stop_instance failed")
            return "تعذر إيقاف القالب."

    tid = str(slots.get("template_id") or ud.get("template_id") or "").strip()
    if not tid:
        return "تعذر تحديد القالب."

    try:
        from lumen.templates.service import get_template_service
        from lumen.templates.models import TemplateLaunchMode, TemplateInstanceStatus

        svc = get_template_service()
        if effect == "tpl_reserve_trial":
            try:
                mins = int(slots.get("trial_minutes") or 0)
            except (TypeError, ValueError):
                mins = 0
            # Product default: if minutes never set (stale UI), use 15
            if mins <= 0:
                mins = 15
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
                "owner_admin_id": int(user_id),
                "owner_user_id": int(user_id),
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
            from lumen.templates.host_adapter import prepare_permanent_launch
            from lumen.bot.ui.project_resolve import bind_active_repo

            plan = prepare_permanent_launch(int(user_id), template_id=tid)
            if not plan.ok or not plan.pending_host:
                return _deny_ar(plan.reason)
            ud["pending_host"] = dict(plan.pending_host)
            ud.pop("pending_run", None)
            ud.pop("pending_live_run", None)
            ud.pop("pending_deploy", None)
            if plan.instance is not None:
                ud["last_template_instance_id"] = plan.instance.instance_id
            bind_active_repo(ud, plan.project_path, entry=plan.entry_point or "main.py")
            try:
                from lumen.bot.session_store import get_session_store
                if user_id:
                    get_session_store().save(int(user_id), dict(ud))
            except Exception:
                logger.debug("template permanent session persist failed", exc_info=True)

            lines = [
                "تم تجهيز القالب للاستخدام الدائم: " + str(tid),
                "• استضافة دائمة (HostService)",
                "• المدة: 30 يومًا — حد 3 قوالب مجانية شغّالة",
                "• المشروع: `" + str(plan.project_path) + "`",
                "• نقطة الدخول: `" + str(plan.entry_point) + "`",
                "",
                "أرسل توكن البوت من @BotFather لبدء الاستضافة.",
            ]
            body = chr(10).join(lines)
            if message is not None:
                try:
                    from lumen.bot.ui.secret_prompt import prompt_for_secret
                    await prompt_for_secret(
                        message=message, kind="bot", body=body, user_id=int(user_id or 0)
                    )
                    return ""
                except Exception:
                    logger.exception("template permanent secret prompt failed")
            return body

    except Exception as exc:
        logger.exception("template reserve failed effect=%s uid=%s", effect, user_id)
        return _deny_ar(f"{type(exc).__name__}:{str(exc)[:100]}")
    return ""


__all__ = ["execute_template_reserve"]
