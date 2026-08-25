"""Engine Router — DynamicBotSpec → Rule Engine (plan step 4)."""
from __future__ import annotations

from typing import Any

from ..dynamic_bot_spec import DynamicBotSpec, parse_dynamic_spec
from ..rule_engine import run_rule_engine
from .compose import compose_infinite_from_payload


def route_and_execute(
    spec: DynamicBotSpec | dict[str, Any],
    event: dict[str, Any],
    *,
    state: dict[str, Any] | None = None,
    mode: str = "interpreter",
    tenant_key: str = "global",
) -> dict[str, Any]:
    dyn = parse_dynamic_spec(spec)
    if mode == "compile_only":
        bot, _ = compose_infinite_from_payload(dyn.model_dump())
        return {"ok": True, "mode": mode, "bot_spec": bot.to_dict(), "actions": []}
    out = run_rule_engine(dyn, event, state=state, tenant_key=tenant_key)
    out["mode"] = mode
    return out
