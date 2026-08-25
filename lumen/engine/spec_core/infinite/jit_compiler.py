"""JIT Spec Compiler — DynamicBotSpec → BotSpec + optional Python handlers.

LLM never writes Python; this renderer is the only path to executable form.
"""
from __future__ import annotations

import json
from pathlib import Path
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


def compile_to_project(spec: DynamicBotSpec | dict[str, Any], out_dir: str | Path) -> str:
    """Write a live-runnable Telegram bot driven by the infinite Rule Engine.

    Embeds the DynamicBotSpec JSON and a minimal PTB host that:
      - maps Telegram updates → events
      - runs run_rule_engine (or embedded run_flow fallback)
      - applies send_message / reply_message results

    Returns project path as str.
    """
    from .ast_validator import validate_dynamic_spec

    dyn = validate_dynamic_spec(spec)
    root = Path(out_dir)
    root.mkdir(parents=True, exist_ok=True)
    app_dir = root / "app"
    app_dir.mkdir(exist_ok=True)
    (app_dir / "__init__.py").write_text("", encoding="utf-8")

    # Persist authoritative DAG
    spec_path = app_dir / "dynamic_spec.json"
    spec_path.write_text(
        json.dumps(dyn.model_dump(), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    # Embedded interpreter (same logic as rule_engine, self-contained for live bots)
    runtime_py = '''"""Infinite live runtime — executes DynamicBotSpec DAG at runtime."""
from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)
_SPEC_PATH = Path(__file__).with_name("dynamic_spec.json")
_STATE: dict[str, Any] = {}
_SAFE_KEY = re.compile(r"^[a-zA-Z_][a-zA-Z0-9_]{0,63}$")
_MAX_WALK = 15


def load_spec() -> dict[str, Any]:
    return json.loads(_SPEC_PATH.read_text(encoding="utf-8"))


def _safe_key(key: str) -> str | None:
    k = (key or "").strip()
    if not k or not _SAFE_KEY.match(k) or k.startswith("__"):
        return None
    return k


def _match_trigger(node: dict, event: dict) -> bool:
    et = str(event.get("type") or "").lower()
    t = (node.get("trigger") or {}).get("type")
    cfg = (node.get("trigger") or {}).get("config") or {}
    if t in {"on_command", "on_start"}:
        if et not in {"on_command", "command", "on_start"}:
            return False
        want = str(cfg.get("command") or ("start" if t == "on_start" else "")).lstrip("/").lower()
        got = str(event.get("command") or "").lstrip("/").lower()
        if t == "on_start" and got in {"start", ""}:
            return True
        return bool(want) and want == got
    if t == "on_message":
        return et in {"on_message", "message"} and not str(event.get("command") or "").strip()
    if t == "on_callback":
        if et not in {"on_callback", "callback"}:
            return False
        want = str(cfg.get("data") or cfg.get("id") or "")
        got = str(event.get("data") or "")
        return (not want) or want == got
    if t == "on_join":
        return et in {"on_join", "new_chat_members"}
    if t == "on_leave":
        return et in {"on_leave", "left_chat_member"}
    if t == "on_payment":
        return et in {"on_payment", "successful_payment"}
    if t == "on_pre_checkout":
        return et in {"on_pre_checkout", "pre_checkout_query"}
    if t == "on_webhook":
        return et in {"on_webhook", "webhook"}
    if t == "on_schedule":
        return et in {"on_schedule", "schedule"}
    return False


def _cond_ok(cond: dict, *, text: str, is_admin: bool, state: dict, event: dict) -> bool:
    t = cond.get("type")
    cfg = cond.get("config") or {}
    if t == "always":
        return True
    if t == "user_is_admin":
        return bool(is_admin)
    if t == "user_is_owner":
        return bool(event.get("is_owner") or is_admin)
    if t == "text_contains":
        return str(cfg.get("value") or "").lower() in (text or "").lower()
    if t == "text_equals":
        return (text or "").strip() == str(cfg.get("value") or "")
    if t == "text_regex":
        try:
            return bool(re.search(str(cfg.get("pattern") or ""), text or ""))
        except re.error:
            return False
    if t in {"state_equals", "state_check"}:
        k = _safe_key(str(cfg.get("key") or ""))
        return bool(k) and state.get(k) == cfg.get("value")
    if t == "state_exists":
        k = _safe_key(str(cfg.get("key") or ""))
        return bool(k) and k in state
    if t == "has_payload":
        return bool(event.get("payload") or event.get("data"))
    if t == "payment_currency":
        want = str(cfg.get("currency") or "").upper()
        got = str(event.get("currency") or "").upper()
        return (not want) or want == got
    return True


def _exec_action(action: dict, *, state: dict, text: str) -> dict:
    t = action.get("type")
    cfg = action.get("config") or {}
    if t in {"send_message", "reply_message", "notify_admin"}:
        return {"type": t, "text": str(cfg.get("text") or cfg.get("message") or "")}
    if t in {"update_state", "update_db", "change_state"}:
        k = _safe_key(str(cfg.get("key") or ""))
        if k:
            state[k] = cfg.get("value")
        return {"type": "update_state", "key": k, "value": cfg.get("value")}
    if t == "clear_state":
        k = _safe_key(str(cfg.get("key") or ""))
        if k and k in state:
            del state[k]
        return {"type": "clear_state", "key": k}
    if t == "noop":
        return {"type": "noop"}
    if t == "log_event":
        logger.info("infinite log: %s", cfg.get("message") or cfg.get("text") or "")
        return {"type": "log_event"}
    if t == "answer_precheckout":
        return {"type": "answer_precheckout", "ok": bool(cfg.get("ok", True)), "error_message": str(cfg.get("error_message") or "")}
    return {"type": t or "unknown", "config": cfg}


def run_event(event: dict[str, Any], state: dict[str, Any] | None = None) -> dict[str, Any]:
    """Walk DAG from matching entry triggers."""
    spec = load_spec()
    nodes = list(spec.get("nodes") or [])
    by_id = {n.get("id"): n for n in nodes if n.get("id")}
    st = state if state is not None else _STATE
    text = str(event.get("text") or "")
    is_admin = bool(event.get("is_admin"))
    results: list[dict] = []
    entries = [n for n in nodes if _match_trigger(n, event)]
    for entry in entries:
        node = entry
        steps = 0
        while node is not None and steps < _MAX_WALK:
            steps += 1
            if not all(_cond_ok(c, text=text, is_admin=is_admin, state=st, event=event) for c in (node.get("conditions") or [])):
                break
            for act in node.get("actions") or []:
                results.append({"node_id": node.get("id"), **_exec_action(act, state=st, text=text)})
            nxt = node.get("next_node_id")
            node = by_id.get(nxt) if nxt else None
    return {"ok": True, "results": results, "state": dict(st)}
'''
    (app_dir / "infinite_runtime.py").write_text(runtime_py, encoding="utf-8")

    main_py = f'''"""Live infinite bot — generated by Lumen JIT compiler.
Bot: {dyn.bot_name}
Engine: infinite_v1 (atomic DAG / rule engine)
"""
from __future__ import annotations

import logging
import os
from pathlib import Path

from telegram import Update
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    ChatMemberHandler,
    CommandHandler,
    MessageHandler,
    PreCheckoutQueryHandler,
    filters,
)

from app.infinite_runtime import run_event

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("infinite_bot")
STATE: dict = {{}}


async def _dispatch(update: Update, context, event: dict) -> None:
    out = run_event(event, state=STATE)
    chat = update.effective_chat
    if not chat:
        return
    for item in out.get("results") or []:
        t = item.get("type")
        if t in {{"send_message", "reply_message", "notify_admin"}} and item.get("text"):
            await context.bot.send_message(chat_id=chat.id, text=str(item["text"])[:4000])
        elif t == "answer_precheckout" and update.pre_checkout_query:
            await update.pre_checkout_query.answer(
                ok=bool(item.get("ok", True)),
                error_message=str(item.get("error_message") or "") or None,
            )


async def on_text(update: Update, context) -> None:
    msg = update.effective_message
    user = update.effective_user
    if not msg:
        return
    text = msg.text or msg.caption or ""
    cmd = ""
    if text.startswith("/"):
        cmd = text[1:].split()[0].split("@")[0].lower()
        et = "on_command" if cmd else "on_message"
    else:
        et = "on_message"
    await _dispatch(update, context, {{
        "type": et,
        "text": text,
        "command": cmd,
        "is_admin": bool(user and getattr(user, "id", None) in set(context.application.bot_data.get("admin_ids") or [])),
        "user_id": getattr(user, "id", None),
    }})


async def on_callback(update: Update, context) -> None:
    q = update.callback_query
    if not q:
        return
    await q.answer()
    await _dispatch(update, context, {{
        "type": "on_callback",
        "data": q.data or "",
        "text": q.data or "",
        "is_admin": False,
    }})


async def on_pre_checkout(update: Update, context) -> None:
    q = update.pre_checkout_query
    if not q:
        return
    await _dispatch(update, context, {{
        "type": "on_pre_checkout",
        "currency": getattr(q, "currency", "") or "",
        "payload": getattr(q, "invoice_payload", "") or "",
        "is_admin": False,
    }})


async def on_payment(update: Update, context) -> None:
    msg = update.effective_message
    if not msg or not msg.successful_payment:
        return
    sp = msg.successful_payment
    await _dispatch(update, context, {{
        "type": "on_payment",
        "currency": sp.currency,
        "payload": sp.invoice_payload,
        "total_amount": sp.total_amount,
        "is_admin": False,
    }})


def main() -> None:
    token = (os.getenv("TELEGRAM_BOT_TOKEN") or "").strip()
    if not token:
        raise SystemExit("TELEGRAM_BOT_TOKEN required")
    app = Application.builder().token(token).build()
    app.add_handler(MessageHandler(filters.TEXT | filters.COMMAND, on_text))
    app.add_handler(CallbackQueryHandler(on_callback))
    app.add_handler(PreCheckoutQueryHandler(on_pre_checkout))
    app.add_handler(MessageHandler(filters.SUCCESSFUL_PAYMENT, on_payment))
    logger.info("infinite bot starting name={dyn.bot_name}")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
'''
    (root / "main.py").write_text(main_py, encoding="utf-8")
    (root / "requirements.txt").write_text(
        "python-telegram-bot>=21.0,<22\npython-dotenv>=1.0.0\n",
        encoding="utf-8",
    )
    (root / ".env.example").write_text("TELEGRAM_BOT_TOKEN=\n", encoding="utf-8")
    (root / "README.md").write_text(
        f"# {dyn.bot_name}\n\nInfinite engine bot (atomic DAG).\n\n"
        f"```bash\npip install -r requirements.txt\n"
        f"export TELEGRAM_BOT_TOKEN=...\npython main.py\n```\n",
        encoding="utf-8",
    )
    return str(root.resolve())
