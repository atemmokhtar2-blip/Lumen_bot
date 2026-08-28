"""Pure engine UI controller — phases, buttons, apply_action."""
from __future__ import annotations

from dataclasses import dataclass

from .catalog import get_action, is_known_action
from .models import EngineUiPhase, EngineUiState, UiButton
from .presets import BOT_TYPE_PRESETS, preset_description, preset_label


@dataclass(frozen=True)
class ApplyResult:
    state: EngineUiState
    ok: bool
    message_ar: str
    buttons: tuple[tuple[UiButton, ...], ...]
    # Side-effect hint for bot layer (not executed here)
    run_generation: bool = False
    generation_request: str = ""


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


def buttons_for_phase(phase: EngineUiPhase) -> tuple[tuple[UiButton, ...], ...]:
    if phase in {EngineUiPhase.HOME, EngineUiPhase.IDLE}:
        return _home_buttons()
    if phase == EngineUiPhase.GEN_TYPE:
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
    if phase == EngineUiPhase.GEN_CONFIRM:
        return (
            (
                UiButton("نعم، ابدأ التوليد", "confirm_generate"),
                UiButton("لا، تعديل", "open_generate"),
            ),
            (UiButton("إلغاء", "cancel_generate"),),
        )
    if phase == EngineUiPhase.GENERATING:
        return ((UiButton("القائمة", "home"),),)
    if phase == EngineUiPhase.GEN_DONE:
        return (
            (UiButton("إنشاء بوت آخر", "open_generate"),),
            (UiButton("لوحة التحكم", "open_dashboard"),),
            (UiButton("القائمة", "home"),),
        )
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


def missing_for_state(state: EngineUiState) -> list[str]:
    if state.phase in {EngineUiPhase.GEN_TYPE}:
        if not (state.slots.get("bot_type") or "").strip():
            return ["bot_type"]
        if state.slots.get("bot_type") == "custom" and not (
            state.slots.get("bot_description") or ""
        ).strip():
            return ["bot_description"]
        return []
    if state.phase == EngineUiPhase.GEN_CONFIRM:
        miss = []
        if not (state.slots.get("bot_description") or "").strip():
            miss.append("bot_description")
        return miss
    return list(state.missing)


def composed_request(state: EngineUiState) -> str:
    desc = (state.slots.get("bot_description") or "").strip()
    if desc:
        return desc
    tid = (state.slots.get("bot_type") or "").strip()
    return preset_description(tid).strip()


def apply_action(state: EngineUiState, action_id: str, arg: str = "") -> ApplyResult:
    action_id = (action_id or "").strip().lower()
    arg = (arg or "").strip()[:40]
    if not is_known_action(action_id):
        return ApplyResult(
            state=state,
            ok=False,
            message_ar="إجراء غير معروف.",
            buttons=buttons_for_phase(state.phase),
        )
    spec = get_action(action_id)
    assert spec is not None
    if state.phase not in spec.allowed_phases:
        return ApplyResult(
            state=state,
            ok=False,
            message_ar="هذا الإجراء غير متاح في المرحلة الحالية.",
            buttons=buttons_for_phase(state.phase),
        )

    new = EngineUiState(
        phase=state.phase,
        slots=dict(state.slots),
        missing=list(state.missing),
        project_ref=state.project_ref,
        plane=state.plane,
        last_action=action_id,
        version=state.version,
    )
    run_gen = False
    gen_req = ""

    if action_id == "home":
        new.phase = EngineUiPhase.HOME
        new.slots.pop("awaiting_text", None)
        new.missing = []
        msg = "القائمة الرئيسية."
    elif action_id == "open_generate":
        new.phase = EngineUiPhase.GEN_TYPE
        new.slots.pop("confirmed", None)
        new.missing = missing_for_state(new)
        msg = "اختر نوع البوت."
    elif action_id == "await_generate_text":
        new.phase = EngineUiPhase.GEN_TYPE
        new.slots["bot_type"] = "custom"
        new.slots["awaiting_text"] = "1"
        new.missing = missing_for_state(new)
        msg = "اكتب وصف البوت."
    elif action_id == "pick_type":
        if arg not in BOT_TYPE_PRESETS:
            return ApplyResult(
                state=state,
                ok=False,
                message_ar="نوع غير معروف.",
                buttons=buttons_for_phase(state.phase),
            )
        new.slots["bot_type"] = arg
        if arg == "custom":
            new.phase = EngineUiPhase.GEN_TYPE
            new.slots["awaiting_text"] = "1"
            new.slots.pop("bot_description", None)
            msg = "اكتب وصف البوت المخصص في الشات."
        else:
            new.slots["bot_description"] = preset_description(arg)
            new.slots.pop("awaiting_text", None)
            new.phase = EngineUiPhase.GEN_CONFIRM
            msg = f"تم اختيار: {preset_label(arg)}"
        new.missing = missing_for_state(new)
    elif action_id == "confirm_generate":
        req = composed_request(new)
        if not req:
            new.phase = EngineUiPhase.GEN_TYPE
            new.slots["awaiting_text"] = "1"
            new.missing = ["bot_description"]
            msg = "لا يوجد وصف — اكتب وصف البوت أولاً."
        else:
            new.slots["confirmed"] = "1"
            new.phase = EngineUiPhase.GENERATING
            new.missing = []
            run_gen = True
            gen_req = req
            msg = "بدء التوليد."
    elif action_id == "cancel_generate":
        new.phase = EngineUiPhase.HOME
        new.slots.pop("awaiting_text", None)
        new.slots.pop("confirmed", None)
        new.missing = []
        msg = "تم إلغاء التوليد الموجّه."
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
    elif action_id == "noop":
        msg = "تم."
    else:
        return ApplyResult(
            state=state,
            ok=False,
            message_ar="إجراء غير منفَّذ.",
            buttons=buttons_for_phase(state.phase),
        )

    new.missing = missing_for_state(new)
    return ApplyResult(
        state=new,
        ok=True,
        message_ar=msg,
        buttons=buttons_for_phase(new.phase),
        run_generation=run_gen,
        generation_request=gen_req,
    )
