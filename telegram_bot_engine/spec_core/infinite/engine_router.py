"""Engine router — execute DynamicBotSpec via rule interpreter or compiled handlers."""
from __future__ import annotations

import logging
from typing import Any

from .api_proxy import proxy_request
from .ast_validator import validate_dynamic_spec
from .infinite_schema import DynamicBotSpec
from .jit_compiler import compile_dynamic_spec, render_handlers_python

logger = logging.getLogger(__name__)


def route_and_execute(
    spec: DynamicBotSpec | dict[str, Any],
    event: dict[str, Any],
    *,
    state: dict[str, Any] | None = None,
    mode: str = "interpreter",
    tenant_key: str = "global",
) -> dict[str, Any]:
    """
    mode:
      - interpreter: run in-process rule engine (default)
      - python: exec generated run_flow module
      - compile_only: return BotSpec dict only
    """
    dyn = validate_dynamic_spec(spec)
    state = dict(state or {})

    if mode == "compile_only":
        bot = compile_dynamic_spec(dyn)
        return {"ok": True, "mode": mode, "bot_spec": bot.to_dict(), "actions": []}

    if mode == "python":
        code = render_handlers_python(dyn)
        ns: dict[str, Any] = {}
        exec(compile(code, "<infinite_handlers>", "exec"), ns)
        actions = ns["run_flow"](event, state)
    else:
        actions = _interpret(dyn, event, state)

    # Execute side-effect actions that need proxy
    results = []
    for item in actions:
        act = item.get("action") if isinstance(item, dict) else item
        if not isinstance(act, dict):
            results.append(item)
            continue
        at = act.get("type")
        cfg = act.get("config") or {}
        if at in {"call_external_api", "call_api"}:
            url = str(cfg.get("url") or "")
            pr = proxy_request(
                url,
                method=str(cfg.get("method") or "GET"),
                json_body=cfg.get("json") if isinstance(cfg.get("json"), dict) else None,
                tenant_key=tenant_key,
            )
            results.append({"node_id": item.get("node_id"), "action": at, "proxy": pr})
        else:
            results.append(item)

    return {"ok": True, "mode": mode, "state": state, "actions": results}


def _interpret(dyn: DynamicBotSpec, event: dict[str, Any], state: dict[str, Any]) -> list[dict[str, Any]]:
    text = str(event.get("text") or "")
    is_admin = bool(event.get("is_admin"))
    etype = str(event.get("type") or "on_message")
    cmd = str(event.get("command") or "")
    out: list[dict[str, Any]] = []

    def cond_ok(cond) -> bool:
        t = cond.type
        cfg = cond.config or {}
        if t == "always":
            return True
        if t in {"user_is_admin", "user_is_owner"}:
            return is_admin
        if t == "text_contains":
            return str(cfg.get("value") or "").lower() in text.lower()
        if t == "text_equals":
            return text.strip() == str(cfg.get("value") or "")
        if t in {"state_equals", "state_check"}:
            return state.get(str(cfg.get("key") or "")) == cfg.get("value")
        if t == "state_exists":
            return str(cfg.get("key") or "") in state
        if t == "time_between":
            return True  # host may refine with clock
        return True

    for node in dyn.nodes:
        trig = node.trigger
        cfg = trig.config or {}
        match = False
        if trig.type == "on_message" and etype in {"on_message", "message"}:
            match = True
        elif trig.type in {"on_command", "on_start"} and etype in {"on_command", "command", "on_start"}:
            want = str(cfg.get("command") or ("start" if trig.type == "on_start" else "")).lstrip("/")
            match = cmd.lstrip("/") == want or (trig.type == "on_start" and cmd in {"start", ""})
        elif trig.type == "on_callback" and etype in {"on_callback", "callback"}:
            match = str(event.get("data") or "") == str(cfg.get("data") or cfg.get("id") or "")
        elif trig.type in {"on_schedule", "on_webhook"} and etype == trig.type:
            match = True
        if not match:
            continue
        if not all(cond_ok(c) for c in node.conditions):
            continue
        for act in node.actions:
            out.append({"node_id": node.id, "action": act.model_dump()})
            if act.type in {"update_state", "update_db", "change_state"}:
                k = str((act.config or {}).get("key") or "")
                if k:
                    state[k] = (act.config or {}).get("value")
    return out
