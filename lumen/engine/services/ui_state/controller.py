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
from .navigation import go_back, go_home, record_transition, stack_clear
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
            UiButton("✨ إنشاء بوت", "open_generate", style="success"),
            UiButton("📦 القوالب", "open_templates", style="success"),
        ),
        (
            UiButton("📊 لوحة التحكم", "open_dashboard", style="primary"),
            UiButton("💎 الرصيد", "open_billing", style="primary"),
        ),
        (
            UiButton("⚙️ الإعدادات", "open_settings", style="primary"),
            UiButton("❓ المساعدة", "open_help"),
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




def _template_gallery_buttons() -> tuple[tuple[UiButton, ...], ...]:
    """One row per catalog template — detail opens via tpl_select."""
    try:
        from lumen.templates.service import get_template_service
        specs = list(get_template_service().list_catalog())
    except Exception:
        try:
            from lumen.templates.service import TemplateService
            specs = list(TemplateService().list_catalog())
        except Exception:
            specs = []
    rows: list[tuple[UiButton, ...]] = []
    rows.append((UiButton("🤖 بوتاتي من القوالب", "tpl_mine", style="primary"),))
    for spec in specs[:12]:
        rows.append((UiButton(spec.title[:40], "tpl_select", spec.short_id or spec.id, style="primary"),))
    if len(rows) == 1:
        rows.append((UiButton("📭 لا توجد قوالب", "open_templates"),))
    return _with_nav(tuple(rows), EngineUiPhase.TEMPLATES)


def _template_status_buttons(state: EngineUiState) -> tuple[tuple[UiButton, ...], ...]:
    """Stop buttons use short index arg (signed callback ≤12)."""
    rows: list[tuple[UiButton, ...]] = []
    for i in range(5):
        iid = (state.slots.get(f"tpl_i{i}") or "").strip()
        if not iid:
            continue
        st = (state.slots.get(f"tpl_s{i}") or "?")[:12]
        title = (state.slots.get(f"tpl_t{i}") or f"#{i+1}")[:24]
        rem = (state.slots.get(f"tpl_r{i}") or "")[:16]
        label = f"{title} · {st}"
        if rem:
            label = f"{title} · {st} · {rem}"
        rows.append((UiButton(label[:40], "tpl_refresh_mine"),))
        if st in {"running", "preparing", "شغال", "شغّال", "تجهيز", "قيد التجهيز"}:
            rows.append((UiButton(f"⏹ إيقاف #{i+1}", "tpl_stop", str(i), style="danger"),))
    rows.append(
        (
            UiButton("🔄 تحديث", "tpl_refresh_mine", style="primary"),
            UiButton("📦 رجوع للقوالب", "nav_back"),
        )
    )
    return _with_nav(tuple(rows), EngineUiPhase.TEMPLATE_STATUS)


def _template_detail_buttons(template_id: str) -> tuple[tuple[UiButton, ...], ...]:
    # Always use short_id in callback arg (Telegram signed arg ≤12)
    tid = _template_arg_code(template_id)
    return _with_nav(
        (
            (
                UiButton("⏱ تجربة مؤقتة", "tpl_trial", tid, style="primary"),
                UiButton("🚀 استخدام دائم", "tpl_permanent", tid, style="success"),
            ),
            (UiButton("🤖 بوتاتي", "tpl_mine", style="primary"), UiButton("📦 رجوع للقوالب", "nav_back"),),
        ),
        EngineUiPhase.TEMPLATE_DETAIL,
    )


def _template_arg_code(template_id: str) -> str:
    """Map full or short id → short code safe for signed callbacks."""
    raw = (template_id or "").strip()
    if not raw:
        return ""
    try:
        from lumen.templates.service import TemplateService
        spec = TemplateService().get_catalog_item(raw)
        if spec is not None:
            return (spec.short_id or spec.id)[:6]
    except Exception:
        pass
    return raw[:6]


def _template_minutes_buttons(template_id: str) -> tuple[tuple[UiButton, ...], ...]:
    tid = _template_arg_code(template_id)
    # Product: max 50 minutes; offer common buckets
    choices = (5, 15, 30, 50)
    rows: list[tuple[UiButton, ...]] = []
    row: list[UiButton] = []
    for m in choices:
        row.append(UiButton(f"⏱ {m} دقيقة", "tpl_minutes", f"{tid}:{m}", style="primary"))
        if len(row) == 2:
            rows.append(tuple(row))
            row = []
    if row:
        rows.append(tuple(row))
    rows.append((UiButton("◀️ رجوع", "nav_back"),))  # tid is short code
    return _with_nav(tuple(rows), EngineUiPhase.TEMPLATE_TRIAL_MINUTES)


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
            return _with_nav(((UiButton("✅ متابعة للتأكيد", "to_confirm"),),), phase)
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
                UiButton("⏭ تخطي هذا", "skip_need"),
                UiButton("🚀 توليد بما هو متاح", "to_confirm"),
            )
        )
        return _with_nav(tuple(rows), phase)

    if phase == EngineUiPhase.GEN_CONFIRM:
        rem = remaining_needs(state.needs or [], state.slots)
        rows = []
        if rem:
            # engine still wants something — offer continue slots or force generate
            rows.append((UiButton("✏️ أكمل الناقص", "resume_slots"),))
        rows.append(
            (
                UiButton("✅ نعم، ابدأ التوليد", "confirm_generate", style="success"),
                UiButton("✏️ تعديل", "open_generate"),
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
                    UiButton("🧪 تجربة في الشات", "post_trial", style="success"),
                    UiButton("🚀 استضافة دائمة", "post_host", style="success"),
                )
            )
            rows.append(
                (
                    UiButton("📦 تحميل ZIP", "post_zip", style="primary"),
                    UiButton("👁 معاينة الملفات", "post_preview", style="primary"),
                )
            )
        rows.append((UiButton("✨ إنشاء بوت آخر", "open_generate", style="success"),))
        rows.append((UiButton("📊 لوحة التحكم", "open_dashboard", style="primary"),))
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
                    UiButton("📡 حالة", "dash_status", str(i), style="primary"),
                    UiButton("⏹ إيقاف", "dash_stop", str(i), style="danger"),
                    UiButton("🩺 تشخيص", "dash_diagnose", str(i), style="primary"),
                )
            )
        rows.append(
            (
                UiButton("🔄 تحديث القائمة", "open_dashboard", style="primary"),
                UiButton("📡 حالة الكل", "dash_status", "all", style="primary"),
            )
        )
        rows.append(
            (
                UiButton("🧪 تجربة المشروع", "dash_trial", style="success"),
                UiButton("🚀 استضافة المشروع", "post_host", style="success"),
            )
        )
        rows.append((UiButton("✨ إنشاء بوت", "open_generate", style="success"),))
        return _with_nav(tuple(rows), phase)
    if phase == EngineUiPhase.BILLING:
        rows: list[tuple[UiButton, ...]] = [
            (UiButton("🔄 تحديث الرصيد", "open_billing", style="primary"),),
        ]
        # Pro plan revealed only after "عرض المزيد" (keeps keyboard short)
        if (state.slots or {}).get("billing_expanded") == "1":
            rows.append(
                (UiButton("🚀 Lumen Pro", "view_pro_plan", style="success"),),
            )
        else:
            rows.append(
                (UiButton("➕ عرض المزيد", "show_more_plans", style="primary"),),
            )
        return _with_nav(tuple(rows), phase)
    if phase == EngineUiPhase.PRO_PLAN:
        return _with_nav(
            (
                (UiButton(f"اشترك — {PRO_PLAN_PRICE_STARS} ⭐", "buy_pro_plan", style="success"),),
                (UiButton("💎 رجوع للرصيد", "nav_back", style="primary"),),
            ),
            phase,
        )
    if phase == EngineUiPhase.HELP:
        return _with_nav((), phase)
    if phase == EngineUiPhase.SETTINGS:
        return _with_nav(_settings_buttons(), phase)
    if phase == EngineUiPhase.REFERRAL:
        return _with_nav(_referral_buttons(), phase)
    if phase == EngineUiPhase.CONNECTIONS:
        return _with_nav(_connections_buttons(), phase)
    if phase == EngineUiPhase.CONN_GITHUB:
        return _with_nav(_conn_github_buttons(state), phase)
    if phase == EngineUiPhase.TEMPLATES:
        return _template_gallery_buttons()
    if phase == EngineUiPhase.TEMPLATE_STATUS:
        return _template_status_buttons(state)
    if phase == EngineUiPhase.TEMPLATE_DETAIL:
        tid = (state.slots.get("template_short") or state.slots.get("template_id") or "").strip()
        return _template_detail_buttons(tid)
    if phase == EngineUiPhase.TEMPLATE_TRIAL_MINUTES:
        tid = (state.slots.get("template_short") or state.slots.get("template_id") or "").strip()
        return _template_minutes_buttons(tid)
    if phase == EngineUiPhase.CONTEXT:

        kind = (state.slots or {}).get("ui_event") or ""
        return _with_nav(buttons_for_event(kind), phase)
    return _with_nav((), phase)


def _settings_buttons() -> tuple[tuple[UiButton, ...], ...]:
    return (
        (UiButton("🔗 الاتصالات", "open_connections", style="primary"),),
        (UiButton("🎁 الإحالة — $5", "open_referral", style="success"),),
    )


def _referral_buttons() -> tuple[tuple[UiButton, ...], ...]:
    return (
        (UiButton("🔄 تحديث", "open_referral", style="primary"),),
    )


def _connections_buttons() -> tuple[tuple[UiButton, ...], ...]:
    return (
        (UiButton("🐙 GitHub", "conn_github", style="success"),),
        (UiButton("⚙️ رجوع للإعدادات", "nav_back", style="primary"),),
    )


def _conn_github_buttons(state: EngineUiState) -> tuple[tuple[UiButton, ...], ...]:
    """Static chrome; dynamic repo rows are injected by callback_router."""
    rows: list[tuple[UiButton, ...]] = []
    # Repo buttons encoded in slots: gh_r0_id / gh_r0_title … by router
    for i in range(12):
        rid = (state.slots or {}).get(f"gh_r{i}_id") or ""
        title = (state.slots or {}).get(f"gh_r{i}_title") or ""
        if not rid or not title:
            break
        rows.append((UiButton(title[:60], "conn_gh_select", rid, style="primary"),))
    connected = (state.slots or {}).get("gh_connected") == "1"
    if not connected:
        rows.append((UiButton("🐙 اتصل بـ GitHub", "conn_gh_connect", style="success"),))
        rows.append((UiButton("🔑 ربط يدوي (PAT)", "conn_gh_pat", style="primary"),))
    else:
        rows.append(
            (
                UiButton("🔄 تحديث القائمة", "conn_gh_refresh", style="primary"),
                UiButton("🔁 إعادة الربط", "conn_gh_connect", style="primary"),
            )
        )
        rows.append(
            (
                UiButton("📜 سجل النشاط", "conn_gh_activity", style="primary"),
                UiButton("🔌 فصل الاتصال", "conn_gh_disconnect", style="danger"),
            )
        )
    page = int((state.slots or {}).get("gh_page") or "1")
    nav_row: list[UiButton] = []
    if page > 1:
        nav_row.append(UiButton("◀ السابق", "conn_gh_page", f"p:{page - 1}", style="primary"))
    if (state.slots or {}).get("gh_has_more") == "1":
        nav_row.append(UiButton("▶️ التالي", "conn_gh_page", f"p:{page + 1}", style="primary"))
    if nav_row:
        rows.append(tuple(nav_row))
    # Phase 3: trial/host only when workspace ready (after deep understand + env)
    if (state.slots or {}).get("gh_bound_ok") == "1" and (state.slots or {}).get("gh_ready") == "1":
        rows.append(
            (
                UiButton("🧪 تجربة في الشات", "post_trial", style="success"),
                UiButton("🚀 استضافة دائمة", "post_host", style="success"),
            )
        )
    elif (state.slots or {}).get("gh_bound_ok") == "1" and (state.slots or {}).get("gh_ready") == "0":
        rows.append((UiButton("✏️ أكمِل المتغيرات", "conn_gh_refresh", style="primary"),))
    rows.append((UiButton("🔗 رجوع للاتصالات", "nav_back", style="primary"),))
    return tuple(rows)


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



def _fill_template_status_slots(state: EngineUiState, user_id: int | None) -> EngineUiState:
    """Load user template instances into slots tpl_i* for the status panel."""
    for i in range(5):
        state.slots.pop(f"tpl_i{i}", None)
        state.slots.pop(f"tpl_s{i}", None)
        state.slots.pop(f"tpl_t{i}", None)
        state.slots.pop(f"tpl_r{i}", None)
        state.slots.pop(f"tpl_m{i}", None)
    if not user_id:
        return state
    try:
        from lumen.templates.host_adapter import list_user_status, reconcile_expired

        reconcile_expired(int(user_id), stop_hosts=False)
        rows = list_user_status(int(user_id))[:5]
        for i, row in enumerate(rows):
            state.slots[f"tpl_i{i}"] = row.instance_id
            state.slots[f"tpl_s{i}"] = row.status  # Arabic label for display
            state.slots[f"tpl_t{i}"] = row.title[:40]
            state.slots[f"tpl_r{i}"] = row.remaining_label_ar[:20]
            state.slots[f"tpl_m{i}"] = row.mode
    except Exception:
        pass
    return state

def apply_action(
    state: EngineUiState, action_id: str, arg: str = "", *, user_id: int | None = None
) -> ApplyResult:
    action_id = (action_id or "").strip().lower()
    arg = (arg or "").strip()[:64]
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

    # ── Path: Navigation (single entry) ───────────────────────────
    if action_id == "nav_back":
        def _rn(s: EngineUiState) -> EngineUiState:
            return _refresh_needs(s, user_id=user_id)
        new, msg = go_back(new, refresh_needs=_rn)
    elif action_id == "home":
        go_home(new)
        msg = "القائمة الرئيسية."
    # ── Path: Generate ───────────────────────────────────────────
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
    # ── Path: Dashboard ──────────────────────────────────────────
    elif action_id == "open_dashboard":
        new.phase = EngineUiPhase.DASHBOARD
        new.missing = []
        msg = "لوحة التحكم."
    # ── Path: Billing ────────────────────────────────────────────
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
    # ── Path: Help ───────────────────────────────────────────────
    elif action_id == "open_help":
        new.phase = EngineUiPhase.HELP
        new.missing = []
        msg = "المساعدة."
    # ── Path: Settings / Connections / Referral ──────────────────
    elif action_id == "open_settings":
        new.phase = EngineUiPhase.SETTINGS
        new.missing = []
        msg = "الإعدادات."
    elif action_id == "open_referral":
        new.phase = EngineUiPhase.REFERRAL
        new.missing = []
        msg = "برنامج الإحالة — $5."
    # ── Path: Templates ──────────────────────────────────────────
    elif action_id == "open_templates":
        new.phase = EngineUiPhase.TEMPLATES
        new.slots.pop("template_id", None)
        new.slots.pop("template_title", None)
        new.slots.pop("template_description", None)
        new.missing = []
        if user_id:
            try:
                from lumen.templates.host_adapter import reconcile_expired
                reconcile_expired(int(user_id), stop_hosts=False)
            except Exception:
                pass
        msg = "قوالب جاهزة — اختر بوتًا للعرض."
    elif action_id == "tpl_mine" or action_id == "tpl_refresh_mine":
        new.phase = EngineUiPhase.TEMPLATE_STATUS
        new = _fill_template_status_slots(new, user_id)
        new.missing = []
        msg = "بوتاتك من القوالب."
    elif action_id == "tpl_stop":
        new.phase = EngineUiPhase.TEMPLATE_STATUS
        idx = (arg or "").strip()
        iid = (new.slots.get(f"tpl_i{idx}") or "").strip() if idx.isdigit() else ""
        new.slots["tpl_stop_target"] = iid
        new.missing = []
        msg = "جاري إيقاف القالب…"
        post_fx = "tpl_stop_instance"
    elif action_id == "tpl_select":
        tid = (arg or "").strip()
        try:
            from lumen.templates.service import TemplateService
            spec = TemplateService().get_catalog_item(tid)
        except Exception:
            spec = None
        if spec is None:
            return ApplyResult(
                state=state,
                ok=False,
                message_ar="القالب غير موجود.",
                buttons=buttons_for_state(state),
            )
        new.phase = EngineUiPhase.TEMPLATE_DETAIL
        new.slots["template_id"] = spec.id
        new.slots["template_short"] = spec.short_id
        new.slots["template_title"] = spec.title
        new.slots["template_description"] = (spec.description or "")[:500]
        new.missing = []
        msg = spec.title
    elif action_id == "tpl_trial":
        code = (arg or new.slots.get("template_short") or new.slots.get("template_id") or "").strip()
        try:
            from lumen.templates.service import TemplateService
            spec = TemplateService().get_catalog_item(code)
        except Exception:
            spec = None
        if spec is None:
            return ApplyResult(state=state, ok=False, message_ar="القالب غير موجود.", buttons=buttons_for_state(state))
        new.slots["template_id"] = spec.id
        new.slots["template_short"] = spec.short_id
        new.phase = EngineUiPhase.TEMPLATE_TRIAL_MINUTES
        new.missing = []
        msg = "اختر مدة التجربة (حتى 50 دقيقة)."
    elif action_id == "tpl_minutes":
        parts = (arg or "").split(":", 1)
        code = (parts[0] if parts else new.slots.get("template_short") or new.slots.get("template_id") or "").strip()
        try:
            mins = int(parts[1]) if len(parts) > 1 else 0
        except ValueError:
            mins = 0
        try:
            from lumen.templates.service import TemplateService
            spec = TemplateService().get_catalog_item(code)
        except Exception:
            spec = None
        if spec is None:
            return ApplyResult(state=state, ok=False, message_ar="القالب غير موجود.", buttons=buttons_for_state(state))
        new.slots["template_id"] = spec.id
        new.slots["template_short"] = spec.short_id
        new.slots["trial_minutes"] = str(mins)
        new.phase = EngineUiPhase.TEMPLATE_DETAIL
        new.missing = []
        msg = f"تجربة مؤقتة — {mins} دقيقة (قيد التجهيز)."
        post_fx = "tpl_reserve_trial"
    elif action_id == "tpl_permanent":
        code = (arg or new.slots.get("template_short") or new.slots.get("template_id") or "").strip()
        try:
            from lumen.templates.service import TemplateService
            spec = TemplateService().get_catalog_item(code)
        except Exception:
            spec = None
        if spec is None:
            return ApplyResult(state=state, ok=False, message_ar="القالب غير موجود.", buttons=buttons_for_state(state))
        new.slots["template_id"] = spec.id
        new.slots["template_short"] = spec.short_id
        new.phase = EngineUiPhase.TEMPLATE_DETAIL
        new.missing = []
        msg = "استخدام دائم — حتى 30 يومًا (قيد التجهيز)."
        post_fx = "tpl_reserve_permanent"
    elif action_id == "open_connections":
        new.phase = EngineUiPhase.CONNECTIONS
        new.missing = []
        msg = "الاتصالات."
    elif action_id == "conn_github":
        new.phase = EngineUiPhase.CONN_GITHUB
        new.slots["gh_page"] = "1"
        new.missing = []
        msg = "GitHub."
    elif action_id == "conn_gh_connect":
        new.phase = EngineUiPhase.CONN_GITHUB
        new.slots.pop("gh_await_pat", None)
        new.slots["gh_await_app"] = "1"
        new.missing = []
        msg = "افتح GitHub لتثبيت التطبيق وربط حسابك."
    elif action_id == "conn_gh_pat":
        new.phase = EngineUiPhase.CONN_GITHUB
        new.slots["gh_await_pat"] = "1"
        new.slots.pop("gh_await_app", None)
        new.missing = []
        msg = "ربط يدوي: أرسل توكن GitHub (PAT)."
    elif action_id == "conn_gh_disconnect":
        new.phase = EngineUiPhase.CONN_GITHUB
        new.slots["gh_await_disconnect"] = "1"
        new.missing = []
        msg = "تأكيد فصل GitHub؟ سيتم حذف الأسرار نهائيًا."
    elif action_id == "conn_gh_disconnect_confirm":
        new.phase = EngineUiPhase.CONN_GITHUB
        new.slots["gh_connected"] = "0"
        new.slots["gh_login"] = ""
        new.slots.pop("gh_await_pat", None)
        new.slots.pop("gh_await_app", None)
        new.slots.pop("gh_await_disconnect", None)
        new.missing = []
        msg = "تم فصل اتصال GitHub."
    elif action_id == "conn_gh_activity":
        new.phase = EngineUiPhase.CONN_GITHUB
        new.missing = []
        msg = "سجل نشاط GitHub."
    elif action_id == "gh_confirm_push":
        new.missing = []
        msg = "تأكيد الدفع إلى GitHub…"
    elif action_id == "gh_cancel_push":
        new.missing = []
        msg = "أُلغي الدفع."
    elif action_id == "conn_gh_refresh":
        new.phase = EngineUiPhase.CONN_GITHUB
        new.slots["gh_page"] = new.slots.get("gh_page") or "1"
        new.missing = []
        msg = "تحديث مستودعات GitHub…"
    elif action_id == "conn_gh_page":
        new.phase = EngineUiPhase.CONN_GITHUB
        if arg.startswith("p:"):
            try:
                new.slots["gh_page"] = str(max(1, int(arg[2:])))
            except ValueError:
                new.slots["gh_page"] = "1"
        msg = "صفحة المستودعات."
        new.missing = []
    elif action_id == "conn_gh_select":
        new.phase = EngineUiPhase.CONN_GITHUB
        rid = (arg or "").strip()[:40]
        new.slots["gh_selected_id"] = rid
        # full_name/url filled by router from repo cache after select
        msg = "تم اختيار المستودع."
        new.missing = []
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
    # ── Path: Dashboard host ops ─────────────────────────────────
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
    # ── Path: Post-generate delivery ─────────────────────────────
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

    # Single navigation bookkeeping path (see navigation.py)
    record_transition(action_id=action_id, previous=state.phase, new_state=new)
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


