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
from .presets import BOT_TYPE_PRESETS, preset_description, preset_label


@dataclass(frozen=True)
class ApplyResult:
    state: EngineUiState
    ok: bool
    message_ar: str
    buttons: tuple[tuple[UiButton, ...], ...]
    run_generation: bool = False
    generation_request: str = ""
    post_side_effect: str = ""


def _home_buttons() -> tuple[tuple[UiButton, ...], ...]:
    return (
        (
            UiButton("إنشاء بوت جديد", "open_generate"),
            UiButton("لوحة التحكم", "open_dashboard"),
        ),
        (
            UiButton("الرصيد والخطة", "open_billing"),
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
        # Soft type chips + free text — still entry points to engine path
        return (
            (
                UiButton("متجر", "pick_type", "shop"),
                UiButton("إشعارات", "pick_type", "notify"),
            ),
            (
                UiButton("مهام", "pick_type", "tasks"),
                UiButton("محادثة", "pick_type", "chat"),
            ),
            (UiButton("مخصص — اكتب وصفاً", "pick_type", "custom"),),
            (UiButton("القائمة", "home"),),
        )

    if phase == EngineUiPhase.GEN_SLOTS:
        rem = remaining_needs(state.needs or [], state.slots)
        if not rem:
            return (
                (UiButton("متابعة للتأكيد", "to_confirm"),),
                (UiButton("القائمة", "home"),),
            )
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
        rows.append((UiButton("إلغاء", "cancel_generate"),))
        return tuple(rows)

    if phase == EngineUiPhase.GEN_CONFIRM:
        rem = remaining_needs(state.needs or [], state.slots)
        rows = []
        if rem:
            # engine still wants something — offer continue slots or force generate
            rows.append((UiButton("أكمل الناقص", "resume_slots"),))
        rows.append(
            (
                UiButton("نعم، ابدأ التوليد", "confirm_generate"),
                UiButton("تعديل", "open_generate"),
            )
        )
        rows.append((UiButton("إلغاء", "cancel_generate"),))
        return tuple(rows)

    if phase == EngineUiPhase.GENERATING:
        return ((UiButton("القائمة", "home"),),)
    if phase == EngineUiPhase.GEN_DONE:
        rows = []
        if (state.project_ref or "").strip():
            rows.append(
                (
                    UiButton("تجربة في الشات", "post_trial"),
                    UiButton("استضافة دائمة", "post_host"),
                )
            )
            rows.append(
                (
                    UiButton("تحميل ZIP", "post_zip"),
                    UiButton("معاينة الملفات", "post_preview"),
                )
            )
        rows.append((UiButton("إنشاء بوت آخر", "open_generate"),))
        rows.append(
            (
                UiButton("لوحة التحكم", "open_dashboard"),
                UiButton("القائمة", "home"),
            )
        )
        return tuple(rows)
    if phase == EngineUiPhase.DASHBOARD:
        return (
            (
                UiButton("تحديث", "open_dashboard"),
                UiButton("إنشاء بوت", "open_generate"),
            ),
            (UiButton("القائمة", "home"),),
        )
    if phase == EngineUiPhase.BILLING:
        return (
            (UiButton("تحديث الخطة", "open_billing"),),
            (UiButton("القائمة", "home"),),
        )
    if phase == EngineUiPhase.HELP:
        return ((UiButton("القائمة", "home"),),)
    return ((UiButton("القائمة", "home"),),)


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

    if action_id == "home":
        new.phase = EngineUiPhase.HOME
        new.slots.pop("awaiting_text", None)
        new.missing = []
        msg = "القائمة الرئيسية."
    elif action_id == "open_generate":
        new.phase = EngineUiPhase.GEN_TYPE
        new.slots.pop("confirmed", None)
        new.missing = missing_for_state(new)
        msg = "اختر نوعاً أو اكتب وصفاً — المحرك سيحدد الناقص."
    elif action_id == "await_generate_text":
        new.phase = EngineUiPhase.GEN_TYPE
        new.slots["bot_type"] = "custom"
        new.slots["awaiting_text"] = "1"
        msg = "اكتب وصف البوت."
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
    elif action_id == "open_help":
        new.phase = EngineUiPhase.HELP
        new.missing = []
        msg = "المساعدة."
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
    )
