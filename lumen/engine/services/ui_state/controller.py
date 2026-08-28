"""Pure engine UI controller — apply actions, compute missing, propose buttons."""
from __future__ import annotations

from dataclasses import dataclass

from .catalog import get_action, is_known_action
from .models import EngineUiPhase, EngineUiState, UiButton


@dataclass(frozen=True)
class ApplyResult:
    state: EngineUiState
    ok: bool
    message_ar: str
    buttons: tuple[tuple[UiButton, ...], ...]


def _home_buttons() -> tuple[tuple[UiButton, ...], ...]:
    return (
        (
            UiButton("🤖 إنشاء بوت جديد", "open_generate"),
            UiButton("📊 لوحة التحكم", "open_dashboard"),
        ),
        (
            UiButton("💳 الرصيد والخطة", "open_billing"),
            UiButton("❓ المساعدة", "open_help"),
        ),
    )


def buttons_for_phase(phase: EngineUiPhase) -> tuple[tuple[UiButton, ...], ...]:
    if phase in {EngineUiPhase.HOME, EngineUiPhase.IDLE}:
        return _home_buttons()
    if phase == EngineUiPhase.GEN_TYPE:
        return (
            (UiButton("✍️ اكتب الوصف في الشات", "await_generate_text"),),
            (UiButton("🔙 القائمة", "home"),),
        )
    if phase == EngineUiPhase.DASHBOARD:
        return (
            (
                UiButton("🔄 تحديث", "open_dashboard"),
                UiButton("🤖 إنشاء بوت", "open_generate"),
            ),
            (UiButton("🔙 القائمة", "home"),),
        )
    if phase == EngineUiPhase.BILLING:
        return (
            (UiButton("🔄 تحديث الخطة", "open_billing"),),
            (UiButton("🔙 القائمة", "home"),),
        )
    if phase == EngineUiPhase.HELP:
        return ((UiButton("🔙 القائمة", "home"),),)
    return ((UiButton("🔙 القائمة", "home"),),)


def missing_for_state(state: EngineUiState) -> list[str]:
    if state.phase == EngineUiPhase.GEN_TYPE:
        if not (state.slots.get("bot_description") or state.slots.get("bot_type") or "").strip():
            if state.slots.get("awaiting_text") == "1":
                return ["bot_description"]
            return ["bot_description"]
        return []
    if state.phase == EngineUiPhase.GEN_CONFIRM:
        miss: list[str] = []
        if not (state.slots.get("bot_description") or "").strip():
            miss.append("bot_description")
        if not (state.slots.get("confirmed") or "").strip():
            miss.append("confirmed")
        return miss
    return list(state.missing)


def apply_action(state: EngineUiState, action_id: str, arg: str = "") -> ApplyResult:
    action_id = (action_id or "").strip().lower()
    arg = (arg or "").strip()[:40]
    if not is_known_action(action_id):
        return ApplyResult(
            state=state,
            ok=False,
            message_ar="إجراء غير معروف — تم التجاهل.",
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

    if action_id == "home":
        new.phase = EngineUiPhase.HOME
        new.slots.pop("awaiting_text", None)
        new.missing = []
        msg = "القائمة الرئيسية."
    elif action_id == "open_generate":
        new.phase = EngineUiPhase.GEN_TYPE
        new.slots["awaiting_text"] = "1"
        new.missing = missing_for_state(new)
        msg = "اكتب وصف البوت في الشات."
    elif action_id == "await_generate_text":
        new.phase = EngineUiPhase.GEN_TYPE
        new.slots["awaiting_text"] = "1"
        new.missing = missing_for_state(new)
        msg = "في انتظار وصف البوت نصاً."
    elif action_id == "open_dashboard":
        new.phase = EngineUiPhase.DASHBOARD
        new.missing = []
        msg = "لوحة التحكم."
    elif action_id == "open_billing":
        new.phase = EngineUiPhase.BILLING
        new.missing = []
        msg = "الخطة والرصيد."
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
    )
