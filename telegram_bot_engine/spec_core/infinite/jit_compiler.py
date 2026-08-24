"""JIT Spec Compiler — DynamicBotSpec → BotSpec + optional Python handlers.

LLM never writes Python; this renderer is the only path to executable form.
"""
from __future__ import annotations

import json
from typing import Any

from ..schema import (
    Action,
    BotMeta,
    BotSpec,
    Feature,
    Messages,
    Trigger,
)
from .ast_validator import validate_dynamic_spec
from .infinite_schema import DynamicBotSpec, FlowNode


def _trigger_to_legacy(node: FlowNode) -> Trigger:
    t = node.trigger.type
    cfg = node.trigger.config or {}
    if t in {"on_command", "on_start"}:
        cmd = str(cfg.get("command") or cfg.get("id") or ("start" if t == "on_start" else node.id))
        return Trigger("command", cmd.lstrip("/"))
    if t == "on_callback":
        return Trigger("callback", str(cfg.get("data") or cfg.get("id") or node.id))
    # on_message / schedule / webhook → message trigger with node id
    return Trigger("message", str(cfg.get("id") or node.id))


def _feature_key_for_node(node: FlowNode) -> str:
    """Map atom action to closest registry capability for deterministic emit."""
    acts = [a.type for a in node.actions]
    if "send_message" in acts or "reply_message" in acts:
        if node.trigger.type in {"on_start"}:
            return "start"
        if node.trigger.type == "on_command":
            cmd = str((node.trigger.config or {}).get("command") or "").lower()
            if cmd in {"help", "start", "about", "ping"}:
                return cmd if cmd != "start" else "start"
            return "help"
        return "help"
    if "call_external_api" in acts:
        return "ping"  # safe placeholder capability; runtime uses infinite interpreter
    return "help"


def compile_dynamic_spec(spec: DynamicBotSpec | dict[str, Any]) -> BotSpec:
    """Validate then compile infinite DAG into classic BotSpec features."""
    dyn = validate_dynamic_spec(spec)
    features: list[Feature] = []
    for node in dyn.nodes:
        feat_key = _feature_key_for_node(node)
        msg = ""
        for a in node.actions:
            if a.type in {"send_message", "reply_message"}:
                msg = str((a.config or {}).get("text") or (a.config or {}).get("message") or msg)
        features.append(
            Feature(
                id=node.id,
                feature=feat_key,
                actor="admin" if any(c.type == "user_is_admin" for c in node.conditions) else "user",
                trigger=_trigger_to_legacy(node),
                action=Action("infinite", node.id),
                messages=Messages(success=msg or f"OK:{node.id}"),
                success={"infinite_node": node.id},
            )
        )
    # Ensure start exists
    if not any(f.feature == "start" or (f.trigger.type == "command" and f.trigger.id == "start") for f in features):
        features.insert(
            0,
            Feature(
                id="auto_start",
                feature="start",
                trigger=Trigger("command", "start"),
                action=Action("core", "start"),
                messages=Messages(success=f"مرحباً بك في {dyn.bot_name}"),
            ),
        )
    return BotSpec(
        bot=BotMeta(name=dyn.bot_name, language=dyn.language, description=dyn.description),
        features=features,
        hard_constraints=["engine:infinite_v1"],
        seed_data={
            "_infinite_spec": [dyn.model_dump()],
            "_engine": [{"name": "infinite_v1"}],
        },
    )


def render_handlers_python(spec: DynamicBotSpec | dict[str, Any]) -> str:
    """Emit a pure-Python rule interpreter module for the DAG (no LLM code)."""
    dyn = validate_dynamic_spec(spec)
    nodes_json = json.dumps([n.model_dump() for n in dyn.nodes], ensure_ascii=False, indent=2)
    return f'''"""Auto-generated infinite rule interpreter — DO NOT hand-edit."""
from __future__ import annotations
import json
from typing import Any

NODES = json.loads("""{nodes_json.replace('"""', "'''")}""")

def _cond_ok(cond: dict, text: str, is_admin: bool, state: dict) -> bool:
    t = cond.get("type")
    cfg = cond.get("config") or {{}}
    if t == "always":
        return True
    if t == "user_is_admin":
        return bool(is_admin)
    if t == "user_is_owner":
        return bool(is_admin)
    if t == "text_contains":
        return str(cfg.get("value") or "").lower() in (text or "").lower()
    if t == "text_equals":
        return (text or "").strip() == str(cfg.get("value") or "")
    if t == "state_equals":
        return state.get(str(cfg.get("key") or "")) == cfg.get("value")
    if t == "state_exists":
        return str(cfg.get("key") or "") in state
    return True

def run_flow(event: dict[str, Any], state: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    """Execute matching nodes; returns list of action dicts for the host runtime."""
    state = state if state is not None else {{}}
    text = str(event.get("text") or "")
    is_admin = bool(event.get("is_admin"))
    etype = str(event.get("type") or "on_message")
    cmd = str(event.get("command") or "")
    out: list[dict[str, Any]] = []
    for node in NODES:
        trig = node.get("trigger") or {{}}
        tt = trig.get("type")
        cfg = trig.get("config") or {{}}
        match = False
        if tt == "on_message" and etype in {{"on_message", "message"}}:
            match = True
        elif tt in {{"on_command", "on_start"}} and etype in {{"on_command", "command"}}:
            want = str(cfg.get("command") or ("start" if tt == "on_start" else "")).lstrip("/")
            match = (cmd.lstrip("/") == want) or (tt == "on_start" and cmd in {{"start", ""}})
        elif tt == "on_callback" and etype in {{"on_callback", "callback"}}:
            match = str(event.get("data") or "") == str(cfg.get("data") or cfg.get("id") or "")
        if not match:
            continue
        if not all(_cond_ok(c, text, is_admin, state) for c in (node.get("conditions") or [])):
            continue
        for act in node.get("actions") or []:
            out.append({{"node_id": node.get("id"), "action": act}})
            if act.get("type") == "update_state":
                k = str((act.get("config") or {{}}).get("key") or "")
                if k:
                    state[k] = (act.get("config") or {{}}).get("value")
    return out
'''
