"""Dashboard actions — real HostService status/stop/diagnose."""
from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger("lumen_bot.ui")


def sync_dashboard_slots(user_id: int, state_slots: dict[str, str]) -> dict[str, str]:
    """Fill dash_h{i} / dash_s{i} from HostService.list_for_user."""
    slots = {k: v for k, v in state_slots.items() if not k.startswith("dash_")}
    try:
        from lumen.bot.config import OUTPUT_DIR
        from lumen.engine.services.hosting import get_hosting_service

        items = get_hosting_service(OUTPUT_DIR).list_for_user(int(user_id))
        # newest first
        items = sorted(items, key=lambda x: getattr(x, "started_at", 0) or 0, reverse=True)
        for i, inst in enumerate(items[:5]):
            iid = str(getattr(inst, "instance_id", "") or "")
            slots[f"dash_h{i}"] = iid
            slots[f"dash_s{i}"] = str(getattr(inst, "status", "") or "")[:20]
            un = str(getattr(inst, "bot_username", "") or "")
            if un:
                slots[f"dash_u{i}"] = un[:32]
    except Exception:
        logger.debug("sync_dashboard_slots failed", exc_info=True)
    return slots


def resolve_instance_id(short: str, slots: dict[str, str]) -> str | None:
    short = (short or "").strip()
    if not short:
        return None
    for i in range(5):
        full = (slots.get(f"dash_h{i}") or "").strip()
        if not full:
            continue
        if full == short or full.endswith(short) or full[-8:] == short:
            return full
    return short if len(short) > 8 else None


async def execute_dash_effect(
    *,
    effect: str,
    target: str,
    user_id: int,
    user_data: dict[str, Any],
    message,
) -> str:
    from lumen.bot.config import OUTPUT_DIR
    from lumen.engine.services.hosting import get_hosting_service

    svc = get_hosting_service(OUTPUT_DIR)
    slots = user_data.get("engine_ui", {}).get("slots") if isinstance(user_data.get("engine_ui"), dict) else {}
    if not slots and isinstance(user_data.get("engine_ui"), dict):
        slots = user_data["engine_ui"].get("slots") or {}
    # load from state_store shape
    try:
        from lumen.bot.ui.state_store import load_ui_state
        st = load_ui_state(user_data)
        slots = st.slots
    except Exception:
        pass

    iid = resolve_instance_id(target, slots or {})
    if effect in {"dash_status", "dash_stop", "dash_diagnose"} and not iid:
        return "لم يُعثر على المثيل — اضغط تحديث."

    import asyncio

    if effect == "dash_status":
        def _st():
            return svc.status(user_id=user_id, instance_id=iid)
        result = await asyncio.to_thread(_st)
        return result.to_user_text()

    if effect == "dash_stop":
        def _sp():
            return svc.stop(instance_id=iid, user_id=user_id)
        result = await asyncio.to_thread(_sp)
        return result.to_user_text()

    if effect == "dash_diagnose":
        def _dg():
            return svc.diagnose(user_id=user_id, instance_id=iid)
        result = await asyncio.to_thread(_dg)
        return result.to_user_text()

    return "إجراء لوحة غير معروف."
