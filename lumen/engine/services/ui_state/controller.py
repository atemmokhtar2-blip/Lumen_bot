"""Engine UI controller — buttons driven by engine needs, not fixed scripts."""
from __future__ import annotations

from dataclasses import dataclass

from .catalog import get_action, is_known_action
from .engine_needs import (
    analyze_needs,
    apply_choice_to_slots,
    enrich_description,
    remaining_needs,
    EngineNeed,
)
from .models import EngineUiPhase, EngineUiState, UiButton
from .pro_plan import PRO_PLAN_PRICE_STARS
from .nav import with_nav as _with_nav
from .presets import BOT_TYPE_PRESETS, preset_description, preset_label
from .ui_events import UiEventKind, apply_event, buttons_for_event


@dataclass(frozen=True)
class ApplyResult:
    state: EngineUiState
    ok: bool
    message_ar: str
    buttons: tuple[tuple[UiButton, ...], ...]
    run_generation: bool = False
    generation_request: str = ""
    post_side_effect: str = ""
    dash_effect: str = ""
    dash_target: str = ""


def _home_buttons() -> tuple[tuple[UiButton, ...], ...]:
    # Bot API 9.4 native colors: success=green, primary=blue, danger=red
    return (
        (
            UiButton("إنشاء بوت", "open_generate", style="success"),
            UiButton("لوحة التحكم", "open_dashboard", style="primary"),
        ),
        (
            UiButton("الرصيد", "open_billing", style="primary"),
            UiButton("الإعدادات", "open_settings", style="primary"),
        ),
        (
            UiButton("المساعدة", "open_help"),
        ),
    )



def _copy_state(state: EngineUiState) -> EngineUiState:
    return EngineUiState(
        phase=state.phase,
        slots=dict(state.slots),
        missing=list(state.missing),
        project_ref=state.project_ref,
        plane=state.plane,
        last_action=state.last_action,
        needs=list(state.needs or []),
        version=state.version,
    )


def _refresh_needs(state: EngineUiState, *, user_id: int | None = None) -> EngineUiState:
    """Recompute needs from current description; drop filled slots from missing."""
    desc = (state.slots.get("bot_description") or "").strip()
    if not desc:
        tid = (state.slots.get("bot_type") or "").strip()
        desc = preset_description(tid)
    if not desc:
        state.needs = []
        state.missing = ["bot_description"] if state.phase != EngineUiPhase.GEN_TYPE else (
            ["bot_type"] if not state.slots.get("bot_type") else []
        )
        return state
    plan = analyze_needs(desc, user_id=user_id)
    state.needs = plan.to_list()
    rem = remaining_needs(state.needs, state.slots)
    state.missing = [n.slot for n in rem]
    if plan.intent_kind:
        state.slots["intent_kind"] = plan.intent_kind
    return state



def buttons_for_state(state: EngineUiState) -> tuple[tuple[UiButton, ...], ...]:
    """Dynamic keyboard from phase + remaining engine needs."""
    phase = state.phase
    if phase in {EngineUiPhase.HOME, EngineUiPhase.IDLE}:
        return _home_buttons()

    if phase == EngineUiPhase.GEN_TYPE:
        # Description-only path — no type chips (user writes free text below)
        return _with_nav((), phase)

    if phase == EngineUiPhase.GEN_SLOTS:
        rem = remaining_needs(state.needs or [], state.slots)
        if not rem:
            return _with_nav(((UiButton("متابعة للتأكيد", "to_confirm"),),), phase)
        need = rem[0]
        rows: list[tuple[UiButton, ...]] = []
        # choice chips in rows of 2
        row: list[UiButton] = []
        for c in need.choices:
            row.append(UiButton(c.label[:32], "fill_slot", c.choice_id))
            if len(row) == 2:
                rows.append(tuple(row))
                row = []
        if row:
            rows.append(tuple(row))
        rows.append(
            (
                UiButton("تخطي هذا", "skip_need"),
                UiButton("توليد بما هو متاح", "to_confirm"),
            )
        )
        return _with_nav(tuple(rows), phase)

    if phase == EngineUiPhase.GEN_CONFIRM:
        rem = remaining_needs(state.needs or [], state.slots)
        rows = []
        if rem:
            # engine still wants something — offer continue slots or force generate
            rows.append((UiButton("أكمل الناقص", "resume_slots"),))
        rows.append(
            (
                UiButton("نعم، ابدأ التوليد", "confirm_generate", style="success"),
                UiButton("تعديل", "open_generate"),
            )
        )
        return _with_nav(tuple(rows), phase)

    if phase == EngineUiPhase.GENERATING:
        return _with_nav((), phase)
    if phase == EngineUiPhase.GEN_DONE:
        rows = []
        if (state.project_ref or "").strip():
            rows.append(
                (
                    UiButton("تجربة في الشات", "post_trial", style="success"),
                    UiButton("استضافة دائمة", "post_host", style="success"),
                )
            )
            rows.append(
                (
                    UiButton("تحميل ZIP", "post_zip", style="primary"),
                    UiButton("معاينة الملفات", "post_preview", style="primary"),
                )
            )
        rows.append((UiButton("إنشاء بوت آخر", "open_generate", style="success"),))
        rows.append((UiButton("لوحة التحكم", "open_dashboard", style="primary"),))
        return _with_nav(tuple(rows), phase)
    if phase == EngineUiPhase.DASHBOARD:
        rows: list[tuple[UiButton, ...]] = []
        # Host rows: dash_h{i}=instance_id; callback arg is index i (stable)
        for i in range(5):
            iid = (state.slots.get(f"dash_h{i}") or "").strip()
            if not iid:
                continue
            st = (state.slots.get(f"dash_s{i}") or "?")[:10]
            un = (state.slots.get(f"dash_u{i}") or "")[:16]
            label = f"#{i+1} {st}"
            if un:
                label = f"#{i+1} @{un} {st}"
            rows.append((UiButton(label[:40], "dash_status", str(i)),))
            rows.append(
                (
                    UiButton("حالة", "dash_status", str(i), style="primary"),
                    UiButton("إيقاف", "dash_stop", str(i), style="danger"),
                    UiButton("تشخيص", "dash_diagnose", str(i), style="primary"),
                )
            )
        rows.append(
            (
                UiButton("تحديث القائمة", "open_dashboard", style="primary"),
                UiButton("حالة الكل", "dash_status", "all", style="primary"),
            )
        )
        rows.append(
            (
                UiButton("تجربة المشروع", "dash_trial", style="success"),
                UiButton("استضافة المشروع", "post_host", style="success"),
            )
        )
        rows.append((UiButton("إنشاء بوت", "open_generate", style="success"),))
        return _with_nav(tuple(rows), phase)
    if phase == EngineUiPhase.BILLING:
        rows: list[tuple[UiButton, ...]] = [
            (UiButton("تحديث الرصيد", "open_billing", style="primary"),),
        ]
        # Pro plan revealed only after "عرض المزيد" (keeps keyboard short)
        if (state.slots or {}).get("billing_expanded") == "1":
            rows.append(
                (UiButton("🚀 Lumen Pro", "view_pro_plan", style="success"),),
            )
        else:
            rows.append(
                (UiButton("عرض المزيد", "show_more_plans", style="primary"),),
            )
        return _with_nav(tuple(rows), phase)
    if phase == EngineUiPhase.PRO_PLAN:
        return _with_nav(
            (
                (UiButton(f"اشترك — {PRO_PLAN_PRICE_STARS} ⭐", "buy_pro_plan", style="success"),),
                (UiButton("رجوع للرصيد", "open_billing", style="primary"),),
            ),
            phase,
        )
    if phase == EngineUiPhase.HELP:
        return _with_nav((), phase)
    if phase == EngineUiPhase.SETTINGS:
        return _with_nav(_settings_buttons(), phase)
    if phase == EngineUiPhase.REFERRAL:
        return _with_nav(_referral_buttons(), phase)
    if phase == EngineUiPhase.CONTEXT:
        kind = (state.slots or {}).get("ui_event") or ""
        return _with_nav(buttons_for_event(kind), phase)
    return _with_nav((), phase)


def _settings_buttons() -> tuple[tuple[UiButton, ...], ...]:
    return (
        (UiButton("الإحالة — $5", "open_referral", style="success"),),
        (UiButton("رجوع", "home", style="primary"),),
    )


def _referral_buttons() -> tuple[tuple[UiButton, ...], ...]:
    return (
        (UiButton("تحديث", "open_referral", style="primary"),),
    )


def buttons_for_phase(phase: EngineUiPhase) -> tuple[tuple[UiButton, ...], ...]:
    return buttons_for_state(EngineUiState(phase=phase))


def missing_for_state(state: EngineUiState) -> list[str]:
    if state.phase == EngineUiPhase.GEN_TYPE:
        if not (state.slots.get("bot_type") or "").strip():
            return ["bot_type"]
        if state.slots.get("bot_type") == "custom" and not (
            state.slots.get("bot_description") or ""
        ).strip():
            return ["bot_description"]
        return []
    if state.phase in {EngineUiPhase.GEN_SLOTS, EngineUiPhase.GEN_CONFIRM}:
        rem = remaining_needs(state.needs or [], state.slots)
        return [n.slot for n in rem]
    return list(state.missing)


def composed_request(state: EngineUiState) -> str:
    desc = (state.slots.get("bot_description") or "").strip()
    if not desc:
        desc = preset_description((state.slots.get("bot_type") or "").strip())
    return enrich_description(desc, state.slots)


def apply_action(
    state: EngineUiState, action_id: str, arg: str = "", *, user_id: int | None = None
) -> ApplyResult:
    action_id = (action_id or "").strip().lower()
    arg = (arg or "").strip()[:40]
    if not is_known_action(action_id):
        return ApplyResult(
            state=state,
            ok=False,
            message_ar="إجراء غير معروف.",
            buttons=buttons_for_state(state),
        )
    spec = get_action(action_id)
    assert spec is not None
    if state.phase not in spec.allowed_phases:
        return ApplyResult(
            state=state,
            ok=False,
            message_ar="هذا الإجراء غير متاح في المرحلة الحالية.",
            buttons=buttons_for_state(state),
        )

    new = _copy_state(state)
    new.last_action = action_id
    run_gen = False
    gen_req = ""
    msg = ""
    post_fx = ""
    dash_fx = ""
    dash_tgt = ""

    if action_id == "nav_back":
        if new.phase == EngineUiPhase.GEN_SLOTS:
            new.phase = EngineUiPhase.GEN_TYPE
            new.slots["awaiting_text"] = "1"
            msg = "رجعت لوصف البوت."
        elif new.phase == EngineUiPhase.GEN_CONFIRM:
            new.phase = EngineUiPhase.GEN_SLOTS
            new = _refresh_needs(new, user_id=user_id)
            msg = "رجعت لأسئلة التوليد."
        elif new.phase == EngineUiPhase.PRO_PLAN:
            new.phase = EngineUiPhase.BILLING
            new.slots["billing_expanded"] = "1"
            new.missing = []
            msg = "الرصيد."
        elif new.phase in {
            EngineUiPhase.DASHBOARD,
            EngineUiPhase.BILLING,
            EngineUiPhase.HELP,
            EngineUiPhase.GEN_DONE,
            EngineUiPhase.CONTEXT,
            EngineUiPhase.GEN_TYPE,
        }:
            new.phase = EngineUiPhase.HOME
            new.slots.pop("awaiting_text", None)
            new.slots.pop("billing_expanded", None)
            new.missing = []
            msg = "القائمة الرئيسية."
        else:
            new.phase = EngineUiPhase.HOME
            msg = "القائمة الرئيسية."
    elif action_id == "home":
        new.phase = EngineUiPhase.HOME
        new.slots.pop("awaiting_text", None)
        new.slots.pop("billing_expanded", None)
        new.slots.pop("pro_buy_requested", None)
        new.missing = []
        msg = "القائمة الرئيسية."
    elif action_id == "open_generate":
        # Jump straight to free-text description — no shop/notify/chat chips
        new.phase = EngineUiPhase.GEN_TYPE
        new.slots["bot_type"] = "custom"
        new.slots["awaiting_text"] = "1"
        new.slots.pop("confirmed", None)
        new.slots.pop("bot_description", None)
        new.needs = []
        new.missing = ["bot_description"]
        msg = "اكتب وصف البوت تحت."
    elif action_id == "await_generate_text":
        new.phase = EngineUiPhase.GEN_TYPE
        new.slots["bot_type"] = "custom"
        new.slots["awaiting_text"] = "1"
        msg = "اكتب وصف البوت تحت."
    elif action_id == "pick_type":
        if arg not in BOT_TYPE_PRESETS:
            return ApplyResult(
                state=state, ok=False, message_ar="نوع غير معروف.", buttons=buttons_for_state(state)
            )
        new.slots["bot_type"] = arg
        if arg == "custom":
            new.phase = EngineUiPhase.GEN_TYPE
            new.slots["awaiting_text"] = "1"
            new.slots.pop("bot_description", None)
            msg = "اكتب وصف البوت المخصص."
        else:
            new.slots["bot_description"] = preset_description(arg)
            new.slots.pop("awaiting_text", None)
            new = _refresh_needs(new, user_id=user_id)
            rem = remaining_needs(new.needs or [], new.slots)
            if rem:
                new.phase = EngineUiPhase.GEN_SLOTS
                msg = f"المحرك يحتاج توضيحاً: {rem[0].text}"
            else:
                new.phase = EngineUiPhase.GEN_CONFIRM
                msg = f"تم اختيار: {preset_label(arg)}"
    elif action_id == "fill_slot":
        rem = remaining_needs(new.needs or [], new.slots)
        if not rem:
            new.phase = EngineUiPhase.GEN_CONFIRM
            msg = "لا يوجد نقص — راجع التأكيد."
        else:
            need = rem[0]
            # match choice on current need
            before = dict(new.slots)
            new.slots = apply_choice_to_slots(new.slots, need, arg)
            if new.slots == before and arg:
                # try match any remaining need
                for n in rem:
                    new.slots = apply_choice_to_slots(new.slots, n, arg)
                    if new.slots.get(n.slot):
                        need = n
                        break
            if new.slots.get("awaiting_text") == "1":
                new.phase = EngineUiPhase.GEN_SLOTS
                msg = f"اكتب قيمة «{need.slot}» في الشات."
            else:
                rem2 = remaining_needs(new.needs or [], new.slots)
                new.missing = [n.slot for n in rem2]
                if rem2:
                    new.phase = EngineUiPhase.GEN_SLOTS
                    msg = rem2[0].text
                else:
                    new.phase = EngineUiPhase.GEN_CONFIRM
                    msg = "اكتملت إجابات المحرك."
    elif action_id == "skip_need":
        rem = remaining_needs(new.needs or [], new.slots)
        if rem:
            # mark skipped so remaining_needs ignores it
            new.slots[rem[0].slot] = new.slots.get(rem[0].slot) or "(تخطي)"
        rem2 = remaining_needs(new.needs or [], new.slots)
        new.missing = [n.slot for n in rem2]
        if rem2:
            new.phase = EngineUiPhase.GEN_SLOTS
            msg = rem2[0].text
        else:
            new.phase = EngineUiPhase.GEN_CONFIRM
            msg = "تم تخطي الناقص — راجع التأكيد."
    elif action_id == "to_confirm":
        new.phase = EngineUiPhase.GEN_CONFIRM
        msg = "مراجعة قبل التوليد."
    elif action_id == "resume_slots":
        new = _refresh_needs(new, user_id=user_id)
        rem = remaining_needs(new.needs or [], new.slots)
        if rem:
            new.phase = EngineUiPhase.GEN_SLOTS
            msg = rem[0].text
        else:
            new.phase = EngineUiPhase.GEN_CONFIRM
            msg = "لا يوجد نقص."
    elif action_id == "confirm_generate":
        req = composed_request(new)
        if not req:
            new.phase = EngineUiPhase.GEN_TYPE
            new.slots["awaiting_text"] = "1"
            msg = "لا يوجد وصف — اكتب وصف البوت."
        else:
            # Platform quota (real plan_gate) before starting engine
            quota_block = False
            quota_detail = ""
            if user_id:
                try:
                    from lumen.platform.plan_gate import check_generation_quota
                    ok_q, reason_q, _info = check_generation_quota(int(user_id))
                    if not ok_q:
                        quota_block = True
                        quota_detail = reason_q or "generation_quota_exceeded"
                except Exception:
                    pass
            if quota_block:
                new = apply_event(new, UiEventKind.INSUFFICIENT_QUOTA, detail=quota_detail)
                msg = "حد الخطة يمنع التوليد الآن."
            else:
                new.slots["confirmed"] = "1"
                new.phase = EngineUiPhase.GENERATING
                run_gen = True
                gen_req = req
                msg = "بدء التوليد."
    elif action_id == "cancel_generate":
        new.phase = EngineUiPhase.HOME
        new.slots.pop("awaiting_text", None)
        new.slots.pop("confirmed", None)
        new.needs = []
        new.missing = []
        msg = "تم الإلغاء."
    elif action_id == "open_dashboard":
        new.phase = EngineUiPhase.DASHBOARD
        new.missing = []
        msg = "لوحة التحكم."
    elif action_id == "open_billing":
        new.phase = EngineUiPhase.BILLING
        new.missing = []
        msg = "الخطة."
    elif action_id == "show_more_plans":
        new.phase = EngineUiPhase.BILLING
        new.slots["billing_expanded"] = "1"
        msg = "خطط إضافية."
    elif action_id == "view_pro_plan":
        new.phase = EngineUiPhase.PRO_PLAN
        new.missing = []
        msg = "🚀 Lumen Pro"
    elif action_id == "buy_pro_plan":
        # Stays on PRO_PLAN; the router sends the Telegram Stars invoice.
        new.phase = EngineUiPhase.PRO_PLAN
        new.slots["pro_buy_requested"] = "1"
        msg = "جارٍ إرسال فاتورة الدفع بنجوم تيليجرام…"
    elif action_id == "open_help":
        new.phase = EngineUiPhase.HELP
        new.missing = []
        msg = "المساعدة."
    elif action_id == "open_settings":
        new.phase = EngineUiPhase.SETTINGS
        new.missing = []
        msg = "الإعدادات."
    elif action_id == "open_referral":
        new.phase = EngineUiPhase.REFERRAL
        new.missing = []
        msg = "برنامج الإحالة — $5."
    elif action_id == "retry_generate":
        req = composed_request(new)
        if not req:
            new.phase = EngineUiPhase.GEN_TYPE
            new.slots["awaiting_text"] = "1"
            msg = "لا وصف لإعادة المحاولة — اكتب وصفاً."
        else:
            new.slots.pop("ui_event", None)
            new.slots.pop("ui_event_detail", None)
            new.phase = EngineUiPhase.GENERATING
            run_gen = True
            gen_req = req
            msg = "إعادة التوليد..."
    elif action_id == "dismiss_event":
        new.slots.pop("ui_event", None)
        new.slots.pop("ui_event_detail", None)
        new.phase = EngineUiPhase.HOME
        msg = "القائمة الرئيسية."
    elif action_id == "dash_status":
        new.phase = EngineUiPhase.DASHBOARD
        dash_fx = "dash_status"
        dash_tgt = arg
        msg = "جلب الحالة من HostService..."
    elif action_id == "dash_stop":
        new.phase = EngineUiPhase.DASHBOARD
        dash_fx = "dash_stop"
        dash_tgt = arg
        msg = "إيقاف المثيل..."
    elif action_id == "dash_diagnose":
        new.phase = EngineUiPhase.DASHBOARD
        dash_fx = "dash_diagnose"
        dash_tgt = arg
        msg = "تشخيص المثيل..."
    
    elif action_id == "dash_logs":
        new.phase = EngineUiPhase.DASHBOARD
        dash_fx = "dash_logs"
        dash_tgt = arg
        msg = "جلب السجلات من HostService..."
    elif action_id == "dash_backup":
        new.phase = EngineUiPhase.DASHBOARD
        dash_fx = "dash_backup"
        dash_tgt = arg
        msg = "نسخ احتياطي لبيانات المشروع..."
    elif action_id == "dash_versions":
        new.phase = EngineUiPhase.DASHBOARD
        dash_fx = "dash_versions"
        dash_tgt = arg
        msg = "قائمة إصدارات النشر..."
    elif action_id == "dash_trial":
        new.phase = EngineUiPhase.DASHBOARD
        # Reuse trial plane on active project
        from .models import RuntimePlaneHint
        new.plane = RuntimePlaneHint.TRIAL_CHAT
        post_fx = "post_trial"
        msg = "تجربة المشروع النشط..."
    elif action_id == "post_trial":

        if not (new.project_ref or "").strip():
            msg = "لا يوجد مشروع — ولّد بوت أولاً."
        else:
            from .models import RuntimePlaneHint
            new.plane = RuntimePlaneHint.TRIAL_CHAT
            msg = "تجربة مؤقتة — أرسل توكن البوت من @BotFather."
            post_fx = "post_trial"
    elif action_id == "post_host":
        if not (new.project_ref or "").strip():
            msg = "لا يوجد مشروع — ولّد بوت أولاً."
        else:
            from .models import RuntimePlaneHint
            new.plane = RuntimePlaneHint.PERMANENT_HOST
            msg = "استضافة دائمة — أرسل توكن البوت من @BotFather."
            post_fx = "post_host"
    elif action_id == "post_zip":
        if not (new.project_ref or "").strip():
            msg = "لا يوجد مشروع لـ ZIP."
        else:
            msg = "تجهيز ZIP..."
            post_fx = "post_zip"
    elif action_id == "post_preview":
        if not (new.project_ref or "").strip():
            msg = "لا يوجد مشروع للمعاينة."
        else:
            msg = "معاينة الملفات..."
            post_fx = "post_preview"
    elif action_id == "noop":
        msg = "تم."
    else:
        return ApplyResult(
            state=state, ok=False, message_ar="إجراء غير منفَّذ.", buttons=buttons_for_state(state)
        )

    new.missing = missing_for_state(new)
    return ApplyResult(
        state=new,
        ok=True,
        message_ar=msg,
        buttons=buttons_for_state(new),
        run_generation=run_gen,
        generation_request=gen_req,
        post_side_effect=post_fx,
        dash_effect=dash_fx,
        dash_target=dash_tgt,
    )
