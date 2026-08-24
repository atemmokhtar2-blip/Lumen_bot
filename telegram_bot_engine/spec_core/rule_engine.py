"""Deterministic Rule Engine for DynamicBotSpec (architecture plan Renderer).

Hardening:
  - Only plan atoms execute
  - State keys sanitized (no path/dunder injection)
  - call_api always via egress proxy (HTTPS + SSRF + rate limit)
  - send_message supports {{text}} after transformers
  - Triggers match strictly (no accidental cross-fire)
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


def _safe_state_key(key: str) -> str | None:
    k = (key or "").strip()
    if not k or not _SAFE_KEY.match(k):
        return None
    if k.startswith("__"):
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
            # Deterministic only — no silent external MT in the rule engine
            out = str(cfg.get("fallback") or out)
        elif tr.type == "summarize":
            try:
                max_len = max(1, min(int(cfg.get("max_len") or 200), 2000))
            except Exception:
                max_len = 200
            out = out[:max_len]
    return out


def _cond(cond: Condition, *, text: str, is_admin: bool, state: dict[str, Any]) -> bool:
    cfg = cond.config or {}
    if cond.type == "user_is_admin":
        return bool(is_admin)
    if cond.type == "text_contains":
        needle = str(cfg.get("value") or "")
        if not needle:
            return False
        return needle.lower() in (text or "").lower()
    if cond.type == "state_equals":
        key = _safe_state_key(str(cfg.get("key") or ""))
        if not key:
            return False
        return state.get(key) == cfg.get("value")
    if cond.type == "time_between":
        try:
            h = datetime.now().hour
            a = int(cfg.get("start_hour") if cfg.get("start_hour") is not None else 0)
            b = int(cfg.get("end_hour") if cfg.get("end_hour") is not None else 23)
            a = max(0, min(23, a))
            b = max(0, min(23, b))
            if a <= b:
                return a <= h <= b
            return h >= a or h <= b
        except Exception:
            return False
    return False


def _match_trigger(node: FlowNode, event: dict[str, Any]) -> bool:
    et = str(event.get("type") or event.get("trigger") or "").strip().lower()
    cfg = node.trigger.config or {}
    t = node.trigger.type

    if t == "on_command":
        if et not in {"on_command", "command"}:
            return False
        want = str(cfg.get("command") or cfg.get("id") or "").lstrip("/").strip().lower()
        got = str(event.get("command") or "").lstrip("/").strip().lower()
        return bool(want) and bool(got) and want == got

    if t == "on_message":
        if et not in {"on_message", "message"}:
            return False
        # Do not fire on_message when a command is present
        if str(event.get("command") or "").strip():
            return False
        return True

    if t == "on_schedule":
        return et in {"on_schedule", "schedule"}

    if t == "on_webhook":
        if et not in {"on_webhook", "webhook"}:
            return False
        want = str(cfg.get("path") or "").strip()
        got = str(event.get("path") or "").strip()
        if want:
            return want == got
        return bool(got)

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
    if action.type == "call_api":
        url = str(cfg.get("url") or "")
        try:
            from .infinite.api_proxy import proxy_request, validate_egress_url

            validate_egress_url(url)  # fail closed before request
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
    """JIT Renderer: validated plan-spec + event → deterministic action results."""
    dyn = parse_dynamic_spec(spec)
    state = dict(state or {})
    # Drop unsafe keys already in state
    state = {k: v for k, v in state.items() if _safe_state_key(str(k))}
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
