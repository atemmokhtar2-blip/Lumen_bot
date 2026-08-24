"""Deterministic Rule Engine — executes DynamicBotSpec as a DAG.

Architecture plan core:
  atoms → validated DAG → walk graph from matching entry nodes
  following next_node_id (not a flat independent loop).

Entry: nodes whose Trigger matches the event.
Then: execute node → follow next_node_id chain (conditions re-checked;
triggers on continuation nodes are optional — chain is sequential flow).
"""
from __future__ import annotations

import logging
import re
from datetime import datetime
from typing import Any

from .dynamic_bot_spec import Action, Condition, DynamicBotSpec, FlowNode, parse_dynamic_spec

logger = logging.getLogger(__name__)

_SAFE_KEY = re.compile(r"^[a-zA-Z_][a-zA-Z0-9_]{0,63}$")
_TEMPLATE = re.compile(r"\{\{\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*\}\}")
_MAX_WALK = 15  # hard stop aligned with MAX_DAG_DEPTH


def _safe_state_key(key: str) -> str | None:
    k = (key or "").strip()
    if not k or not _SAFE_KEY.match(k) or k.startswith("__"):
        return None
    return k


def _render_template(template: str, *, text: str, state: dict[str, Any]) -> str:
    def repl(m: re.Match[str]) -> str:
        name = m.group(1)
        if name == "text":
            return text
        if name in state:
            return str(state[name])
        return ""

    return _TEMPLATE.sub(repl, template or "")


def _apply_transformers(text: str, node: FlowNode) -> str:
    out = text or ""
    for tr in node.transformers:
        cfg = tr.config or {}
        if tr.type == "extract_regex":
            pat = str(cfg.get("pattern") or "")
            if not pat:
                continue
            try:
                m = re.search(pat, out, re.IGNORECASE if cfg.get("ignore_case") else 0)
            except re.error:
                continue
            if not m:
                out = ""
                continue
            grp = cfg.get("group")
            if grp is None:
                out = m.group(1) if m.lastindex else m.group(0)
            else:
                try:
                    out = m.group(int(grp))
                except Exception:
                    out = m.group(0)
        elif tr.type == "translate_text":
            out = str(cfg.get("fallback") or out)
        elif tr.type == "summarize":
            try:
                max_len = max(1, min(int(cfg.get("max_len") or 200), 2000))
            except Exception:
                max_len = 200
            out = out[:max_len]
    return out


def _cond(cond: Condition, *, text: str, is_admin: bool, state: dict[str, Any], event: dict[str, Any] | None = None) -> bool:
    cfg = cond.config or {}
    event = event or {}
    t = cond.type
    if t == "always":
        return True
    if t == "user_is_admin":
        return bool(is_admin)
    if t == "user_is_owner":
        return bool(event.get("is_owner") or is_admin)
    if t == "text_contains":
        needle = str(cfg.get("value") or "")
        if not needle:
            return False
        return needle.lower() in (text or "").lower()
    if t == "text_equals":
        return (text or "").strip() == str(cfg.get("value") or "")
    if t == "text_regex":
        try:
            return bool(re.search(str(cfg.get("pattern") or ""), text or ""))
        except re.error:
            return False
    if t in {"state_equals", "state_check"}:
        key = _safe_state_key(str(cfg.get("key") or ""))
        if not key:
            return False
        return state.get(key) == cfg.get("value")
    if t == "state_exists":
        key = _safe_state_key(str(cfg.get("key") or ""))
        return bool(key) and key in state
    if t == "time_between":
        try:
            h = datetime.now().hour
            a = int(cfg.get("start_hour") if cfg.get("start_hour") is not None else 0)
            b = int(cfg.get("end_hour") if cfg.get("end_hour") is not None else 23)
            a, b = max(0, min(23, a)), max(0, min(23, b))
            if a <= b:
                return a <= h <= b
            return h >= a or h <= b
        except Exception:
            return False
    if t == "has_payload":
        return bool(event.get("payload") or event.get("data"))
    if t == "payment_currency":
        want = str(cfg.get("currency") or "").upper()
        got = str(event.get("currency") or "").upper()
        return (not want) or want == got
    return False


def _match_trigger(node: FlowNode, event: dict[str, Any]) -> bool:
    et = str(event.get("type") or event.get("trigger") or "").strip().lower()
    cfg = node.trigger.config or {}
    t = node.trigger.type

    if t in {"on_command", "on_start"}:
        if et not in {"on_command", "command", "on_start"}:
            return False
        want = str(cfg.get("command") or cfg.get("id") or ("start" if t == "on_start" else "")).lstrip("/").strip().lower()
        got = str(event.get("command") or "").lstrip("/").strip().lower()
        if t == "on_start" and (got in {"start", ""} or et == "on_start"):
            return True
        return bool(want) and bool(got) and want == got

    if t == "on_message":
        if et not in {"on_message", "message"}:
            return False
        if str(event.get("command") or "").strip():
            return False
        return True

    if t == "on_callback":
        if et not in {"on_callback", "callback"}:
            return False
        want = str(cfg.get("data") or cfg.get("id") or "").strip()
        got = str(event.get("data") or event.get("callback_data") or "").strip()
        return (not want) or want == got

    if t == "on_schedule":
        return et in {"on_schedule", "schedule"}

    if t == "on_webhook":
        if et not in {"on_webhook", "webhook"}:
            return False
        want = str(cfg.get("path") or "").strip()
        got = str(event.get("path") or "").strip()
        return want == got if want else bool(got)

    if t == "on_join":
        return et in {"on_join", "chat_member_join", "new_chat_members"}

    if t == "on_leave":
        return et in {"on_leave", "chat_member_leave", "left_chat_member"}

    if t == "on_payment":
        return et in {"on_payment", "successful_payment"}

    if t == "on_pre_checkout":
        return et in {"on_pre_checkout", "pre_checkout_query"}

    return False


def execute_action(
    action: Action,
    *,
    state: dict[str, Any],
    text: str,
    tenant_key: str = "global",
) -> dict[str, Any]:
    cfg = dict(action.config or {})
    if action.type == "send_message":
        raw = str(cfg.get("text") or cfg.get("message") or "")
        return {
            "type": "send_message",
            "text": _render_template(raw, text=text, state=state),
        }
    if action.type == "reply_message":
        raw = str(cfg.get("text") or cfg.get("message") or "")
        return {
            "type": "reply_message",
            "text": _render_template(raw, text=text, state=state),
        }
    if action.type in {"update_state", "update_db", "change_state"}:
        key = _safe_state_key(str(cfg.get("key") or cfg.get("collection") or ""))
        if not key:
            return {"type": action.type, "error": "invalid_key"}
        state[key] = cfg.get("value")
        return {"type": "update_state", "key": key, "value": cfg.get("value")}
    if action.type == "clear_state":
        key = _safe_state_key(str(cfg.get("key") or ""))
        if key and key in state:
            del state[key]
        return {"type": "clear_state", "key": key}
    if action.type == "log_event":
        return {"type": "log_event", "message": str(cfg.get("message") or cfg.get("text") or "")[:500]}
    if action.type == "noop":
        return {"type": "noop"}
    if action.type == "set_command_menu":
        cmds = cfg.get("commands") if isinstance(cfg.get("commands"), list) else []
        return {"type": "set_command_menu", "commands": cmds[:30]}
    if action.type == "notify_admin":
        raw = str(cfg.get("text") or cfg.get("message") or "")
        return {
            "type": "notify_admin",
            "text": _render_template(raw, text=text, state=state),
        }
    if action.type == "answer_precheckout":
        return {
            "type": "answer_precheckout",
            "ok": bool(cfg.get("ok", True)),
            "error_message": str(cfg.get("error_message") or "")[:200],
        }
    if action.type == "update_db":
        key = _safe_state_key(str(cfg.get("key") or cfg.get("collection") or ""))
        if not key:
            return {"type": "update_db", "error": "invalid_key"}
        state[key] = cfg.get("value")
        return {"type": "update_db", "key": key, "value": cfg.get("value")}
    if action.type == "change_state":
        key = _safe_state_key(str(cfg.get("key") or ""))
        if not key:
            return {"type": "change_state", "error": "invalid_key"}
        state[key] = cfg.get("value")
        return {"type": "change_state", "key": key, "value": cfg.get("value")}
    if action.type in {"call_api", "call_external_api", "http_request"}:
        url = str(cfg.get("url") or "")
        try:
            from .infinite.api_proxy import proxy_request, validate_egress_url

            validate_egress_url(url)
            return {
                "type": "call_external_api",
                "result": proxy_request(
                    url,
                    method=str(cfg.get("method") or "GET"),
                    headers=cfg.get("headers") if isinstance(cfg.get("headers"), dict) else None,
                    json_body=cfg.get("json") if isinstance(cfg.get("json"), dict) else None,
                    timeout=float(cfg.get("timeout") or 10.0),
                    tenant_key=tenant_key,
                ),
            }
        except Exception as exc:
            return {"type": "call_external_api", "error": type(exc).__name__, "detail": str(exc)[:200]}

    return {"type": action.type, "error": "unknown_action"}


def _execute_node(
    node: FlowNode,
    *,
    text: str,
    is_admin: bool,
    state: dict[str, Any],
    tenant_key: str,
    results: list[dict[str, Any]],
    event: dict[str, Any] | None = None,
) -> bool:
    """Run one node if conditions pass. Returns True if executed."""
    event = event or {}
    if not all(_cond(c, text=text, is_admin=is_admin, state=state, event=event) for c in node.conditions):
        return False
    local_text = _apply_transformers(text, node)
    for action in node.actions:
        results.append(
            {
                "node_id": node.id,
                **execute_action(
                    action, state=state, text=local_text, tenant_key=tenant_key
                ),
            }
        )
    return True


def run_rule_engine(
    spec: DynamicBotSpec | dict[str, Any],
    event: dict[str, Any],
    *,
    state: dict[str, Any] | None = None,
    tenant_key: str = "global",
) -> dict[str, Any]:
    """Walk the atom DAG: entry triggers → actions → next_node_id chain."""
    dyn = parse_dynamic_spec(spec)
    by_id = {n.id: n for n in dyn.nodes}
    state = {k: v for k, v in dict(state or {}).items() if _safe_state_key(str(k))}
    text = str(event.get("text") or "")
    is_admin = bool(event.get("is_admin"))
    results: list[dict[str, Any]] = []
    graph_paths: list[list[str]] = []

    # Entry nodes = trigger matches event (the graph entry points)
    entries = [n for n in dyn.nodes if _match_trigger(n, event)]

    for entry in entries:
        path = [entry.id]
        node: FlowNode | None = entry
        steps = 0
        while node is not None and steps < _MAX_WALK:
            steps += 1
            executed = _execute_node(
                node,
                text=text,
                is_admin=is_admin,
                state=state,
                tenant_key=tenant_key,
                results=results,
                event=event,
            )
            if not executed:
                # condition failed — stop this chain
                break
            nxt = node.next_node_id
            if not nxt:
                break
            node = by_id.get(nxt)
            if node is None:
                break
            path.append(node.id)
            # Continuation nodes: do not re-require trigger match —
            # they are sequential DAG edges from the entry.
        graph_paths.append(path)

    return {
        "ok": True,
        "bot_name": dyn.bot_name,
        "engine": "rule_engine_v1",
        "dag": True,
        "entry_nodes": [e.id for e in entries],
        "graph_paths": graph_paths,
        "state": state,
        "results": results,
    }
