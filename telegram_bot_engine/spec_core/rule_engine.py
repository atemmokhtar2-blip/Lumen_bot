"""Deterministic Rule Engine for DynamicBotSpec (architecture plan Renderer).

Executes atoms only — never evaluates arbitrary Python from the LLM.
"""
from __future__ import annotations

import logging
import re
import time
from datetime import datetime
from typing import Any

from .dynamic_bot_spec import Action, Condition, DynamicBotSpec, FlowNode, parse_dynamic_spec

logger = logging.getLogger(__name__)


def _apply_transformers(text: str, node: FlowNode) -> str:
    out = text or ""
    for tr in node.transformers:
        cfg = tr.config or {}
        if tr.type == "extract_regex":
            pat = str(cfg.get("pattern") or "")
            if pat:
                m = re.search(pat, out)
                out = m.group(1) if m and m.lastindex else (m.group(0) if m else out)
        elif tr.type == "translate_text":
            # deterministic stub — host may plug real MT; never call external here blindly
            out = str(cfg.get("fallback") or out)
        elif tr.type == "summarize":
            max_len = int(cfg.get("max_len") or 200)
            out = out[:max_len]
    return out


def _cond(cond: Condition, *, text: str, is_admin: bool, state: dict[str, Any]) -> bool:
    cfg = cond.config or {}
    if cond.type == "user_is_admin":
        return bool(is_admin)
    if cond.type == "text_contains":
        return str(cfg.get("value") or "").lower() in (text or "").lower()
    if cond.type == "state_equals":
        return state.get(str(cfg.get("key") or "")) == cfg.get("value")
    if cond.type == "time_between":
        # config: start_hour, end_hour in local time 0-23
        try:
            h = datetime.now().hour
            a = int(cfg.get("start_hour") or 0)
            b = int(cfg.get("end_hour") or 23)
            if a <= b:
                return a <= h <= b
            return h >= a or h <= b
        except Exception:
            return True
    return False


def _match_trigger(node: FlowNode, event: dict[str, Any]) -> bool:
    et = str(event.get("type") or event.get("trigger") or "")
    cfg = node.trigger.config or {}
    t = node.trigger.type
    if t == "on_message" and et in {"on_message", "message", ""}:
        # empty type defaults to message
        if et == "" and event.get("command"):
            return False
        return et in {"on_message", "message"} or (not event.get("command") and et == "")
    if t == "on_command" and et in {"on_command", "command"}:
        want = str(cfg.get("command") or cfg.get("id") or "").lstrip("/")
        got = str(event.get("command") or "").lstrip("/")
        return bool(want) and want == got
    if t == "on_schedule" and et in {"on_schedule", "schedule"}:
        return True
    if t == "on_webhook" and et in {"on_webhook", "webhook"}:
        return str(event.get("path") or "") == str(cfg.get("path") or event.get("path") or "")
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
        return {
            "type": "send_message",
            "text": str(cfg.get("text") or cfg.get("message") or text or ""),
        }
    if action.type == "update_db":
        # deterministic key/value store in state (host persists)
        key = str(cfg.get("key") or cfg.get("collection") or "")
        if key:
            state[key] = cfg.get("value")
        return {"type": "update_db", "key": key, "value": cfg.get("value")}
    if action.type == "change_state":
        key = str(cfg.get("key") or "")
        if key:
            state[key] = cfg.get("value")
        return {"type": "change_state", "key": key, "value": cfg.get("value")}
    if action.type == "call_api":
        url = str(cfg.get("url") or "")
        try:
            from .infinite.api_proxy import proxy_request

            return {
                "type": "call_api",
                "result": proxy_request(
                    url,
                    method=str(cfg.get("method") or "GET"),
                    json_body=cfg.get("json") if isinstance(cfg.get("json"), dict) else None,
                    tenant_key=tenant_key,
                ),
            }
        except Exception as exc:
            return {"type": "call_api", "error": str(exc)[:200]}
    return {"type": action.type, "error": "unknown_action"}


def run_rule_engine(
    spec: DynamicBotSpec | dict[str, Any],
    event: dict[str, Any],
    *,
    state: dict[str, Any] | None = None,
    tenant_key: str = "global",
) -> dict[str, Any]:
    """JIT Renderer path: validated spec + event → action results."""
    dyn = parse_dynamic_spec(spec)
    state = dict(state or {})
    text = str(event.get("text") or "")
    is_admin = bool(event.get("is_admin"))
    results: list[dict[str, Any]] = []

    for node in dyn.nodes:
        if not _match_trigger(node, event):
            continue
        if not all(
            _cond(c, text=text, is_admin=is_admin, state=state) for c in node.conditions
        ):
            continue
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

    return {
        "ok": True,
        "bot_name": dyn.bot_name,
        "engine": "rule_engine_v1",
        "state": state,
        "results": results,
    }
