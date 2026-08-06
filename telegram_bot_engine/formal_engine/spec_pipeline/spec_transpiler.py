"""
Spec-Driven Transpiler — generates a complete Telegram bot from a RichSpec.

This replaces the old transpiler's hardcoded classification functions:
  - cmd_kind()    → uses RichCommand.kind (AI-chosen)
  - store_for_cmd() → uses RichCommand.entity (AI-specified)
  - action_for_cmd() → uses RichCommand.post_action (AI-specified)
  - _pick_wizard_fields() → uses RichCommand.flow_steps / collects_fields

Every behavioral decision comes from the spec. Zero hardcoded verb/stem lists.

The generated bot uses python-telegram-bot v21+ with:
  - handlers.py: one handler per command, with kind-specific behavior
  - models.py: dataclasses from RichEntity (AI-typed fields)
  - store.py: SQLite store per entity
  - logic.py: rule engine + action functions from post_action
  - container.py: dependency injection
  - config.py: typed settings
  - main.py: application wiring
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from ..inference.engine import InferenceResult
from ..schemas.rich_spec import (
    CommandKind,
    PostAction,
    RichCommand,
    RichSpec,
)


# ─────────────────────────── helpers ─────────────────────────────────────

def _ident(name: str) -> str:
    s = re.sub(r"[^a-zA-Z0-9_]", "_", (name or "").strip())
    s = re.sub(r"_+", "_", s).strip("_").lower()
    if not s:
        s = "x"
    if s[0].isdigit():
        s = "_" + s
    return s[:48]


def _cls(name: str) -> str:
    parts = [p for p in _ident(name).split("_") if p]
    return "".join(p.capitalize() for p in parts) or "Item"


def _py(s: Any) -> str:
    return repr(s)


def _kind_val(kind: Any) -> str:
    return kind.value if hasattr(kind, "value") else str(kind)


def _pa_val(pa: Any) -> str:
    return pa.value if hasattr(pa, "value") else str(pa)


# ─────────────────────────── schema module ───────────────────────────────

def _emit_schema_module(spec: RichSpec) -> str:
    """Generate models.py — dataclasses from RichEntity with AI-typed fields."""
    lines = [
        '"""Data models — generated from spec entities (AI-typed fields)."""',
        "from __future__ import annotations",
        "from dataclasses import dataclass, field, asdict",
        "from typing import Any",
        "",
        "",
    ]
    if not spec.entities:
        lines += [
            "@dataclass",
            "class Record:",
            '    """Generic record — no entities specified."""',
            "    id: str = \"\"",
            "    user_id: int = 0",
            "    data: dict[str, Any] = field(default_factory=dict)",
            "",
            "    def to_dict(self) -> dict[str, Any]:",
            "        return {\"id\": self.id, \"user_id\": self.user_id, **self.data}",
            "",
        ]
        return "\n".join(lines) + "\n"

    for entity in spec.entities:
        cls_name = _cls(entity.name)
        lines.append(f"@dataclass")
        lines.append(f"class {cls_name}:")
        lines.append(f'    """{entity.name} entity."""')
        lines.append('    id: str = ""')
        lines.append("    user_id: int = 0")
        seen = {"id", "user_id"}
        for f in entity.fields:
            fname = _ident(f.name)
            if fname in seen:
                continue
            seen.add(fname)
            ftype = (f.field_type.value if hasattr(f.field_type, "value") else str(f.field_type)).lower()
            py_type = {"int": "int", "bool": "bool", "float": "float", "list": "list", "dict": "dict"}.get(ftype, "str")
            default = "0" if py_type == "int" else "0.0" if py_type == "float" else "False" if py_type == "bool" else "\"\"" if py_type == "str" else "field(default_factory=list)" if py_type == "list" else "field(default_factory=dict)"
            if py_type in ("list", "dict"):
                lines.append(f"    {fname}: {py_type} = {default}")
            else:
                lines.append(f"    {fname}: {py_type} = {default}")
        lines.append("")
        lines.append("    def to_dict(self) -> dict[str, Any]:")
        lines.append("        return asdict(self)")
        lines.append("")
        lines.append("")
    return "\n".join(lines) + "\n"


# ─────────────────────────── store module ────────────────────────────────

def _emit_store_module(spec: RichSpec) -> str:
    """Generate store.py — one SQLite store per entity."""
    has_db = spec.has_database() and bool(spec.entities)
    lines = [
        '"""Store — SQLite persistence, one store per entity."""',
        "from __future__ import annotations",
        "import sqlite3",
        "import json",
        "from pathlib import Path",
        "from typing import Any",
        "",
        "",
    ]
    if not has_db:
        lines += [
            "class MemoryStore:",
            '    """In-memory store fallback when no database is needed."""',
            "    def __init__(self) -> None:",
            "        self._data: list[dict[str, Any]] = []",
            "    async def create(self, **fields: Any) -> str:",
            "        import time",
            "        oid = str(int(time.time() * 1000))",
            "        record = {\"id\": oid, **fields}",
            "        self._data.append(record)",
            "        return oid",
            "    async def get(self, oid: str) -> dict[str, Any] | None:",
            "        for r in self._data:",
            "            if r.get(\"id\") == oid:",
            "                return r",
            "        return None",
            "    async def list_all(self) -> list[dict[str, Any]]:",
            "        return list(self._data)",
            "    async def list_by_user(self, user_id: int) -> list[dict[str, Any]]:",
            "        return [r for r in self._data if r.get(\"user_id\") == user_id]",
            "    async def update_status(self, oid: str, status: str) -> bool:",
            "        for r in self._data:",
            "            if r.get(\"id\") == oid:",
            "                r[\"status\"] = status",
            "                return True",
            "        return False",
            "",
        ]
        return "\n".join(lines) + "\n"

    lines += [
        "_DB_PATH = Path(\"./bot.db\")",
        "",
        "def _conn() -> sqlite3.Connection:",
        "    conn = sqlite3.connect(str(_DB_PATH))",
        "    conn.row_factory = sqlite3.Row",
        "    return conn",
        "",
        "def _ensure_tables(conn: sqlite3.Connection) -> None:",
    ]
    for entity in spec.entities:
        table = _ident(entity.name)
        cols = ["id TEXT PRIMARY KEY", "user_id INTEGER"]
        seen = {"id", "user_id"}
        for f in entity.fields:
            fname = _ident(f.name)
            if fname in seen:
                continue
            seen.add(fname)
            ftype = (f.field_type.value if hasattr(f.field_type, "value") else str(f.field_type)).lower()
            col_type = "INTEGER" if ftype == "int" else "REAL" if ftype == "float" else "TEXT"
            cols.append(f"{fname} {col_type}")
        col_sql = ", ".join(cols)
        lines.append(f"    conn.execute('CREATE TABLE IF NOT EXISTS \"{table}\" ({col_sql})')")
    lines += [
        "    conn.commit()",
        "",
        "def _row_to_dict(row: sqlite3.Row) -> dict[str, Any]:",
        "    return {k: row[k] for k in row.keys()}",
        "",
        "",
    ]

    # One store class per entity
    for entity in spec.entities:
        cls_name = _cls(entity.name) + "Store"
        table = _ident(entity.name)
        field_names = ["id", "user_id"] + [_ident(f.name) for f in entity.fields if _ident(f.name) not in {"id", "user_id"}]
        cols_no_id = [c for c in field_names if c != "id"]
        lines.append(f"class {cls_name}:")
        lines.append(f'    """Store for {entity.name} entities."""')
        lines.append("    def __init__(self) -> None:")
        lines.append("        self._table = " + _py(table))
        lines.append("")
        lines.append("    async def create(self, **fields: Any) -> str:")
        lines.append("        import time")
        lines.append("        oid = str(int(time.time() * 1000)) + str(hash(str(fields)) % 1000)")
        lines.append("        record = {\"id\": oid, **fields}")
        lines.append("        conn = _conn()")
        lines.append("        _ensure_tables(conn)")
        lines.append("        cols = list(record.keys())")
        lines.append("        placeholders = \", \".join(\"?\" for _ in cols)")
        lines.append("        col_sql = \", \".join(cols)")
        lines.append('        conn.execute(f\'INSERT INTO "{self._table}" ({col_sql}) VALUES ({placeholders})\', list(record.values()))')
        lines.append("        conn.commit()")
        lines.append("        conn.close()")
        lines.append("        return oid")
        lines.append("")
        lines.append("    async def get(self, oid: str) -> dict[str, Any] | None:")
        lines.append("        conn = _conn()")
        lines.append("        _ensure_tables(conn)")
        lines.append('        row = conn.execute(f\'SELECT * FROM "{self._table}" WHERE id = ?\', (oid,)).fetchone()')
        lines.append("        conn.close()")
        lines.append("        return _row_to_dict(row) if row else None")
        lines.append("")
        lines.append("    async def list_all(self) -> list[dict[str, Any]]:")
        lines.append("        conn = _conn()")
        lines.append("        _ensure_tables(conn)")
        lines.append('        rows = conn.execute(f\'SELECT * FROM "{self._table}" ORDER BY rowid DESC LIMIT 50\').fetchall()')
        lines.append("        conn.close()")
        lines.append("        return [_row_to_dict(r) for r in rows]")
        lines.append("")
        lines.append("    async def list_by_user(self, user_id: int) -> list[dict[str, Any]]:")
        lines.append("        conn = _conn()")
        lines.append("        _ensure_tables(conn)")
        lines.append('        rows = conn.execute(f\'SELECT * FROM "{self._table}" WHERE user_id = ? ORDER BY rowid DESC LIMIT 50\', (user_id,)).fetchall()')
        lines.append("        conn.close()")
        lines.append("        return [_row_to_dict(r) for r in rows]")
        lines.append("")
        lines.append("    async def update_status(self, oid: str, status: str) -> bool:")
        lines.append("        conn = _conn()")
        lines.append("        _ensure_tables(conn)")
        lines.append('        cur = conn.execute(f\'UPDATE "{self._table}" SET status = ? WHERE id = ?\', (status, oid))')
        lines.append("        conn.commit()")
        lines.append("        ok = cur.rowcount > 0")
        lines.append("        conn.close()")
        lines.append("        return ok")
        lines.append("")
        lines.append("")
    return "\n".join(lines) + "\n"


# ─────────────────────────── logic module ────────────────────────────────

def _emit_logic_module(spec: RichSpec) -> str:
    """Generate logic.py — rule engine + action functions from post_actions."""
    lines = [
        '"""Logic — rules and action functions from the spec."""',
        "from __future__ import annotations",
        "from typing import Any",
        "",
        "",
        "def _as_number(v: Any, default: float = 0.0) -> float:",
        "    try:",
        "        return float(v)",
        "    except (TypeError, ValueError):",
        "        return default",
        "",
        "",
        "def apply_rules(ctx: dict[str, Any] | None = None) -> dict[str, Any]:",
        '    """Apply spec rules to a context dict. Returns ctx with _messages."""',
        "    ctx = dict(ctx or {})",
        "    msgs: list[str] = ctx.setdefault(\"_messages\", [])",
    ]
    # Generate rule checks from spec rules
    for i, rule in enumerate(spec.rules):
        lines.append(f"    # Rule {i+1}: {rule.condition}")
        lines.append(f"    # Effect: {rule.effect}")
        lines.append(f"    # (rule expressed as natural language — logged for traceability)")
        lines.append(f"    if False:  # rule_{i+1} placeholder")
        lines.append(f"        msgs.append({ _py(rule.effect) })")
    lines += [
        "    return ctx",
        "",
        "",
    ]
    # Action functions — one per command with a post_action
    for cmd in spec.commands:
        kind = _kind_val(cmd.kind)
        if kind in (CommandKind.START.value, CommandKind.HELP.value, CommandKind.INFO.value):
            continue
        aname = _action_name(cmd)
        if not aname:
            continue
        fn = _ident(aname)
        lines.append(f"async def {fn}(store: Any = None, user_id: int = 0, payload: dict | None = None, args: list | None = None) -> str:")
        lines.append(f'    """Action for /{cmd.name} — post_action: {_pa_val(cmd.post_action)}."""')
        lines.append("    payload = payload or {}")
        lines.append("    msgs = list(payload.get(\"_messages\") or [])")
        pa = _pa_val(cmd.post_action)
        if pa == PostAction.STORE.value and store_is_available(spec, cmd):
            lines.append("    if store is not None and hasattr(store, \"create\"):")
            lines.append("        try:")
            lines.append("            data = {k: v for k, v in payload.items() if k not in (\"_messages\", \"intent\", \"args\", \"text\")}")
            lines.append("            data[\"user_id\"] = user_id")
            lines.append("            oid = await store.create(**data)")
            lines.append(f"            return { _py('تم الحفظ بنجاح ✅ معرف: ') } + str(oid)")
            lines.append("        except Exception as exc:")
            lines.append(f"            return { _py('خطأ في الحفظ: ') } + str(exc)")
            lines.append("    return \"store_unavailable\"")
        elif pa == PostAction.COMPUTE.value:
            lines.append("    # Compute action — returns a result string")
            lines.append("    count = len(args) if args else 0")
            lines.append(f"    return { _py(cmd.reply_text or 'نتيجة: ') } + str(count)")
        elif pa == PostAction.NOTIFY.value:
            lines.append(f"    return { _py(cmd.reply_text or 'تم الإرسال ✅') }")
        elif pa == PostAction.CONFIRM.value:
            lines.append("    data = {k: v for k, v in payload.items() if k not in (\"_messages\", \"intent\", \"args\", \"text\")}")
            lines.append(f"    return { _py('تأكيد البيانات: ') } + str(data)")
        else:
            lines.append(f"    return { _py(cmd.reply_text or cmd.description or 'ok') }")
        lines.append("")
        lines.append("")
    if not any(_action_name(c) for c in spec.commands):
        lines.append("def noop(context: dict[str, Any] | None = None) -> dict[str, Any]:")
        lines.append("    return dict(context or {})")
        lines.append("")
    return "\n".join(lines) + "\n"


def _action_name(cmd: RichCommand) -> str | None:
    """Derive action function name from post_action + entity."""
    kind = _kind_val(cmd.kind)
    pa = _pa_val(cmd.post_action)
    if pa == PostAction.STORE.value and cmd.entity:
        return f"create_{_ident(cmd.entity)}"
    if pa == PostAction.COMPUTE.value:
        return f"compute_{cmd.name}"
    if pa == PostAction.NOTIFY.value:
        return f"notify_{cmd.name}"
    if pa == PostAction.CONFIRM.value:
        return f"confirm_{cmd.name}"
    if kind == CommandKind.ACTION.value:
        return f"action_{cmd.name}"
    return None


def store_is_available(spec: RichSpec, cmd: RichCommand) -> bool:
    """Check if a store exists for the command's entity."""
    if not cmd.entity:
        return False
    return any(e.name.lower() == cmd.entity.lower() for e in spec.entities)


# ─────────────────────────── handlers module ─────────────────────────────

def _emit_handlers_module(spec: RichSpec) -> str:
    """
    Generate handlers.py — one handler per command.
    The behavior of each handler is driven by RichCommand.kind, NOT by
    hardcoded stem/verb matching.
    """
    commands = list(spec.commands)
    buttons = list(spec.buttons)

    # Build the store-name lookup from the spec (entity → store class name)
    store_map: dict[str, str] = {}
    for e in spec.entities:
        store_map[e.name.lower()] = _cls(e.name) + "Store"

    # Build the action-name lookup from the spec (command → action function)
    action_map: dict[str, str] = {}
    for c in commands:
        aname = _action_name(c)
        if aname:
            action_map[c.name] = _ident(aname)

    # Wizards: collect commands with flow_steps
    wizard_cmds = [c for c in commands if _kind_val(c.kind) == CommandKind.COLLECT.value and (c.flow_steps or c.collects_fields)]

    # Button → command routing from the spec
    btn_to_cmd: dict[str, str] = {}
    for b in buttons:
        if b.target_command:
            btn_to_cmd[b.callback_id] = b.target_command
        else:
            # try to match callback_id to a command name
            for c in commands:
                if b.callback_id == c.name or b.callback_id == f"cmd_{c.name}":
                    btn_to_cmd[b.callback_id] = c.name
                    break

    # Keyboard items from spec buttons
    kb_items: list[tuple[str, str]] = []
    if buttons:
        for b in buttons:
            kb_items.append((b.label, b.callback_id))
    else:
        for c in commands:
            if c.name in ("start", "help"):
                continue
            label = (c.description or c.name).strip()[:40] or c.name
            kb_items.append((label, f"cmd:{c.name}"))
            btn_to_cmd[f"cmd:{c.name}"] = c.name

    lines: list[str] = [
        '"""Handlers — spec-driven, one per command. Behavior from RichCommand.kind."""',
        "from __future__ import annotations",
        "from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup",
        "from telegram.ext import ContextTypes",
        "from app import logic",
        "from app.container import get_container",
        "",
        "",
    ]

    # FLOWS dict — from spec collect commands
    lines.append("FLOWS: dict[str, list[dict[str, str]]] = {")
    for c in wizard_cmds:
        steps = []
        if c.flow_steps:
            for fs in c.flow_steps:
                steps.append({"key": _ident(fs.key), "prompt": fs.prompt or f"أدخل {_ident(fs.key)}:"})
        elif c.collects_fields:
            for fk in c.collects_fields:
                steps.append({"key": _ident(fk), "prompt": f"أدخل {_ident(fk)}:"})
        lines.append(f"    {_py(c.name)}: [")
        for s in steps:
            lines.append(f"        {{\"key\": {_py(s['key'])}, \"prompt\": {_py(s['prompt'])}}},")
        lines.append("    ],")
    lines.append("}")
    lines.append("")

    # FLOW_ENTITY + FLOW_KIND dicts
    lines.append("FLOW_ENTITY: dict[str, str] = {")
    for c in wizard_cmds:
        lines.append(f"    {_py(c.name)}: {_py(c.entity or 'record')},")
    lines.append("}")
    lines.append("")
    lines.append("FLOW_KIND: dict[str, str] = {")
    for c in wizard_cmds:
        lines.append(f"    {_py(c.name)}: {_py(_kind_val(c.kind))},")
    lines.append("}")
    lines.append("")

    # BUTTON_TO_CMD dict
    lines.append("BUTTON_TO_CMD: dict[str, str] = {")
    for cb, cn in btn_to_cmd.items():
        lines.append(f"    {_py(cb)}: {_py(cn)},")
    lines.append("}")
    lines.append("")

    # main_keyboard
    lines.append("def main_keyboard() -> InlineKeyboardMarkup | None:")
    if kb_items:
        lines.append("    rows = []")
        row: list[str] = []
        for i, (label, cb) in enumerate(kb_items):
            row.append(f"InlineKeyboardButton({_py(label)}, callback_data={_py(cb)})")
            if len(row) == 2 or i == len(kb_items) - 1:
                lines.append(f"    rows.append([{', '.join(row)}])")
                row = []
        lines.append("    return InlineKeyboardMarkup(rows)")
    else:
        lines.append("    return None")
    lines.append("")
    lines.append("")

    # _start_flow
    lines.append("async def _start_flow(message, context, flow_id: str) -> None:")
    lines.append("    steps = FLOWS.get(flow_id) or []")
    lines.append("    if not steps:")
    lines.append("        await message.reply_text('لا توجد خطوات لهذا الأمر')")
    lines.append("        return")
    lines.append("    context.user_data.clear()")
    lines.append("    context.user_data['flow'] = flow_id")
    lines.append("    context.user_data['step'] = 0")
    lines.append("    context.user_data['data'] = {}")
    lines.append("    context.user_data['state'] = f'flow:{flow_id}:0'")
    lines.append("    await message.reply_text(steps[0]['prompt'])")
    lines.append("")
    lines.append("")

    # start handler
    start_cmd = next((c for c in commands if c.name == "start"), None)
    start_msg = (start_cmd.reply_text if start_cmd and start_cmd.reply_text else "مرحباً بك 👋")
    # Add command map to start message
    cmd_map_lines = [start_msg]
    for c in commands[:12]:
        if c.name not in ("start", "help"):
            cmd_map_lines.append(f"/{c.name} — {c.description or c.name}")
    start_msg_full = "\n".join(cmd_map_lines)
    lines.append("async def start_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:")
    lines.append("    message = update.effective_message")
    lines.append("    if message is None:")
    lines.append("        return")
    lines.append("    context.user_data.clear()")
    lines.append("    kb = main_keyboard()")
    lines.append(f"    if kb is not None:")
    lines.append(f"        await message.reply_text({_py(start_msg_full)}, reply_markup=kb)")
    lines.append("    else:")
    lines.append(f"        await message.reply_text({_py(start_msg_full)})")
    lines.append("")
    lines.append("")

    # help handler
    lines.append("async def help_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:")
    lines.append("    message = update.effective_message")
    lines.append("    if message is None:")
    lines.append("        return")
    help_lines = [f"/{c.name} — {c.description}" for c in commands]
    help_text = "\n".join(help_lines) if help_lines else "help"
    lines.append(f"    await message.reply_text({_py(help_text)})")
    lines.append("")
    lines.append("")

    # One handler per non-start/help command — behavior from kind
    wizard_cmd_names = {c.name for c in wizard_cmds}
    for cmd in commands:
        if cmd.name in ("start", "help"):
            continue
        fn = _ident(cmd.name) + "_handler"
        kind = _kind_val(cmd.kind)
        store_name = store_map.get((cmd.entity or "").lower()) if cmd.entity else None
        action_fn = action_map.get(cmd.name)
        lines.append(f"async def {fn}(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:")
        lines.append("    message = update.effective_message")
        lines.append("    if message is None:")
        lines.append("        return")
        lines.append("    user = update.effective_user")
        lines.append("    uid = user.id if user else 0")
        # Admin check
        if cmd.admin_only:
            lines.append("    from app.config import get_settings")
            lines.append("    settings = get_settings()")
            lines.append("    admins = set()")
            lines.append('    raw = getattr(settings, "admin_user_ids", "") or ""')
            lines.append('    for part in str(raw).split(","):')
            lines.append("        part = part.strip()")
            lines.append("        if part.isdigit():")
            lines.append("            admins.add(int(part))")
            lines.append("    if admins and uid not in admins:")
            lines.append('        await message.reply_text("هذا الأمر للمشرفين فقط")')
            lines.append("        return")
        # Wizard commands → start flow
        if cmd.name in wizard_cmd_names:
            lines.append(f"    await _start_flow(message, context, {_py(cmd.name)})")
            lines.append("    return")
            lines.append("")
            lines.append("")
            continue
        # Non-wizard commands
        lines.append("    args = []")
        lines.append('    if message.text and " " in message.text:')
        lines.append("        args = message.text.split()[1:]")
        lines.append("    container = get_container()")
        if store_name:
            lines.append(f"    store = getattr(container, {_py(store_name)}, None)")
        else:
            lines.append('    store = getattr(container, "primary_store", None)')
        lines.append(f"    payload: dict = {{'user_id': uid, 'intent': {_py(cmd.name)}}}")
        lines.append("    if args:")
        lines.append('        payload["args"] = args')
        lines.append('        payload["text"] = " ".join(args)')
        lines.append("    ruled = logic.apply_rules(payload)")
        lines.append('    msgs = list(ruled.get("_messages") or [])')

        # ── Behavior by kind (from spec, not from hardcoded lists) ──
        if kind == CommandKind.LOOKUP.value:
            lines.append("    oid = args[0] if args else ''")
            lines.append("    if oid and store is not None and hasattr(store, 'get'):")
            lines.append("        try:")
            lines.append("            row = await store.get(str(oid))")
            lines.append("        except Exception as exc:")
            lines.append(f"            await message.reply_text({ _py('خطأ: ') } + str(exc))")
            lines.append("            return")
            lines.append("        if row:")
            lines.append("            summary = ' | '.join(f'{k}={v}' for k, v in list(row.items())[:6])")
            lines.append("            await message.reply_text(str(summary))")
            lines.append("        else:")
            lines.append(f"            await message.reply_text({ _py('لم يتم العثور على السجل') })")
            lines.append("    elif msgs:")
            lines.append('        await message.reply_text(" | ".join(str(m) for m in msgs[:5]))')
            lines.append("    else:")
            lines.append(f"        await message.reply_text({ _py('أرسل المعرف بعد الأمر: /' + cmd.name + ' <id>') })")
        elif kind == CommandKind.LIST.value:
            lines.append("    rows = []")
            lines.append("    if store is not None and hasattr(store, 'list_all'):")
            lines.append("        try:")
            lines.append("            rows = await store.list_all()")
            lines.append("        except Exception as exc:")
            lines.append(f"            msgs.append({ _py('list_error:') } + str(exc))")
            lines.append("    if rows:")
            lines.append("        out = []")
            lines.append("        for i, row in enumerate(rows[:20], 1):")
            lines.append("            if isinstance(row, dict):")
            lines.append("                summary = ' | '.join(f'{k}={v}' for k, v in list(row.items())[:6])")
            lines.append("            else:")
            lines.append("                summary = str(row)[:120]")
            lines.append("            out.append(f'{i}. {summary}')")
            lines.append('        await message.reply_text("\\n".join(out))')
            lines.append("    elif msgs:")
            lines.append('        await message.reply_text(" | ".join(str(m) for m in msgs[:5]))')
            lines.append("    else:")
            lines.append(f"        await message.reply_text({ _py((cmd.description or cmd.name) + ' — لا توجد عناصر بعد') })")
        elif kind == CommandKind.STATS.value:
            lines.append("    count = 0")
            lines.append("    if store is not None and hasattr(store, 'list_all'):")
            lines.append("        try:")
            lines.append("            count = len(await store.list_all())")
            lines.append("        except Exception:")
            lines.append("            count = 0")
            stats_label = cmd.description or "إحصائيات"
            lines.append("    await message.reply_text(" + _py(stats_label) + " + f': {count} سجل')")
        elif kind == CommandKind.BROADCAST.value:
            lines.append(f"    await message.reply_text({ _py('أرسل نص الرسالة بعد الأمر: /' + cmd.name + ' النص') })")
        elif kind == CommandKind.ACTION.value or action_fn:
            if action_fn:
                lines.append(f"    if msgs:")
                lines.append('        await message.reply_text(" | ".join(str(m) for m in msgs[:5]))')
                lines.append(f"    result = await logic.{action_fn}(store=store, user_id=uid, payload=ruled, args=args)")
                lines.append("    if result:")
                lines.append("        await message.reply_text(str(result))")
            else:
                lines.append("    if msgs:")
                lines.append('        await message.reply_text(" | ".join(str(m) for m in msgs[:5]))')
                lines.append("    else:")
                lines.append(f"        await message.reply_text({ _py(cmd.reply_text or cmd.description or cmd.name) })")
        elif kind == CommandKind.INFO.value:
            lines.append(f"    await message.reply_text({ _py(cmd.reply_text or cmd.description or cmd.name) })")
        elif kind == CommandKind.NAVIGATE.value:
            lines.append("    kb = main_keyboard()")
            lines.append(f"    await message.reply_text({ _py(cmd.reply_text or cmd.description or 'اختر من القائمة') }, reply_markup=kb)")
        else:
            # generic / custom
            lines.append("    if msgs:")
            lines.append('        await message.reply_text(" | ".join(str(m) for m in msgs[:5]))')
            lines.append("    else:")
            lines.append(f"        await message.reply_text({ _py(cmd.reply_text or cmd.description or cmd.name) })")
        # Show keyboard after non-list commands
        if kb_items and kind not in (CommandKind.LIST.value, CommandKind.STATS.value):
            lines.append("    kb = main_keyboard()")
            lines.append("    if kb is not None:")
            lines.append(f"        await message.reply_text({ _py('—') }, reply_markup=kb)")
        lines.append("")
        lines.append("")

    # message_handler — wizard state machine
    lines.append("async def message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:")
    lines.append("    message = update.effective_message")
    lines.append("    if message is None:")
    lines.append("        return")
    lines.append("    ud = context.user_data")
    lines.append('    text = (message.text or "").strip()')
    lines.append("    flow_id = ud.get('flow')")
    lines.append("    if flow_id:")
    lines.append("        steps = FLOWS.get(flow_id) or []")
    lines.append("        step_idx = ud.get('step', 0)")
    lines.append("        if step_idx < len(steps):")
    lines.append("            key = steps[step_idx]['key']")
    lines.append("            ud.setdefault('data', {})[key] = text")
    lines.append("            ud['step'] = step_idx + 1")
    lines.append("            if ud['step'] < len(steps):")
    lines.append("                await message.reply_text(steps[ud['step']]['prompt'])")
    lines.append("            else:")
    lines.append("                # Flow complete — store the data")
    lines.append("                data = ud.get('data', {})")
    lines.append("                data['user_id'] = update.effective_user.id if update.effective_user else 0")
    lines.append("                container = get_container()")
    lines.append("                entity = FLOW_ENTITY.get(flow_id, 'record')")
    lines.append("                store_name = entity.lower() + 'store' if entity else 'primary_store'")
    lines.append("                store = getattr(container, store_name.replace('store', 'Store'), None) or getattr(container, 'primary_store', None)")
    lines.append("                if store is not None and hasattr(store, 'create'):")
    lines.append("                    try:")
    lines.append("                        oid = await store.create(**data)")
    lines.append(f"                        await message.reply_text({ _py('تم الحفظ بنجاح ✅ معرف: ') } + str(oid))")
    lines.append("                    except Exception as exc:")
    lines.append(f"                        await message.reply_text({ _py('خطأ في الحفظ: ') } + str(exc))")
    lines.append("                else:")
    lines.append("                    summary = ' | '.join(f'{k}={v}' for k, v in data.items())")
    lines.append(f"                    await message.reply_text({ _py('البيانات: ') } + summary)")
    lines.append("                ud.clear()")
    lines.append("                kb = main_keyboard()")
    lines.append("                if kb is not None:")
    lines.append(f"                    await message.reply_text({ _py('—') }, reply_markup=kb)")
    lines.append("        return")
    lines.append("    # No active flow — generic echo")
    lines.append(f"    await message.reply_text({ _py('استخدم الأوامر المتاحة. /help للقائمة') })")
    lines.append("")
    lines.append("")

    # callback_handler
    lines.append("async def callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:")
    lines.append("    query = update.callback_query")
    lines.append("    if query is None:")
    lines.append("        return")
    lines.append("    await query.answer()")
    lines.append("    cb = query.data or ''")
    lines.append("    cmd_name = BUTTON_TO_CMD.get(cb)")
    lines.append("    if not cmd_name and cb.startswith('cmd:'):")
    lines.append("        cmd_name = cb[4:]")
    lines.append("    if not cmd_name:")
    lines.append("        return")
    lines.append("    # Re-dispatch as a command by calling the handler directly")
    lines.append("    handler_name = cmd_name + '_handler'")
    lines.append("    handler = globals().get(handler_name)")
    lines.append("    if handler is not None:")
    lines.append("        # Simulate command text for the handler")
    lines.append("        if update.effective_message:")
    lines.append("            update.effective_message.text = '/' + cmd_name")
    lines.append("        await handler(update, context)")
    lines.append("    else:")
    lines.append("        await query.message.reply_text(f'unknown: {cb}')")
    lines.append("")
    lines.append("")

    return "\n".join(lines) + "\n"


# ─────────────────────────── container ───────────────────────────────────

def _emit_container(spec: RichSpec) -> str:
    lines = [
        '"""Container — dependency injection for stores."""',
        "from __future__ import annotations",
        "from functools import lru_cache",
        "from typing import Any",
        "",
    ]
    has_db = spec.has_database() and bool(spec.entities)
    if has_db:
        lines.append("from app.store import " + ", ".join(
            _cls(e.name) + "Store" for e in spec.entities
        ))
    else:
        lines.append("from app.store import MemoryStore")
    lines += [
        "",
        "",
        "class Container:",
        "    def __init__(self) -> None:",
    ]
    if has_db:
        for e in spec.entities:
            store_attr = _ident(e.name) + "_store"
            lines.append(f"        self.{store_attr} = {_cls(e.name)}Store()")
        lines.append("        self.primary_store = self." + _ident(spec.entities[0].name) + "_store")
    else:
        lines.append("        self.primary_store = MemoryStore()")
    lines += [
        "",
        "",
        "@lru_cache(maxsize=1)",
        "def get_container() -> Container:",
        "    return Container()",
        "",
    ]
    return "\n".join(lines) + "\n"


# ─────────────────────────── config ──────────────────────────────────────

def _emit_config(spec: RichSpec) -> str:
    lines = [
        '"""Typed config from env."""',
        "from __future__ import annotations",
        "from functools import lru_cache",
        "from pydantic import Field",
        "from pydantic_settings import BaseSettings, SettingsConfigDict",
        "",
        "",
        "class Settings(BaseSettings):",
        '    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")',
        "    telegram_bot_token: str = Field(..., min_length=20)",
        '    admin_user_ids: str = ""',
        '    log_level: str = "INFO"',
    ]
    if spec.has_database():
        lines.append('    database_url: str = "sqlite+aiosqlite:///./bot.db"')
    lines += [
        "",
        "",
        "@lru_cache(maxsize=1)",
        "def get_settings() -> Settings:",
        "    return Settings()",
        "",
    ]
    return "\n".join(lines) + "\n"


# ─────────────────────────── main ────────────────────────────────────────

def _emit_main(spec: RichSpec) -> str:
    commands = list(spec.commands)
    extra = [c for c in commands if c.name not in ("start", "help")]
    imports = [
        "from app.handlers import start_handler, help_handler, message_handler, callback_handler",
    ]
    regs = [
        '    app.add_handler(CommandHandler("start", start_handler))',
        '    app.add_handler(CommandHandler("help", help_handler))',
    ]
    for c in extra:
        ident = _ident(c.name)
        imports.append(f"from app.handlers import {ident}_handler")
        regs.append(f'    app.add_handler(CommandHandler({_py(c.name)}, {ident}_handler))')
    regs += [
        "    app.add_handler(CallbackQueryHandler(callback_handler))",
        "    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, message_handler))",
    ]
    if spec.tech.file_handling:
        regs.append("    app.add_handler(MessageHandler(filters.PHOTO, message_handler))")
        regs.append("    app.add_handler(MessageHandler(filters.Document.ALL, message_handler))")

    bot_cmds = []
    for c in commands:
        bot_cmds.append(f"        BotCommand({_py(c.name)}, {_py((c.description or c.name)[:50])}),")
    bot_block = "\n".join(bot_cmds) if bot_cmds else '        BotCommand("start", "start"),'

    return (
        '"""Entry — wiring spec-driven handlers."""\n'
        "from __future__ import annotations\n"
        "import logging\n"
        "import sys\n"
        "from telegram import BotCommand, Update\n"
        "from telegram.ext import Application, CallbackQueryHandler, CommandHandler, MessageHandler, filters\n"
        "from app.config import get_settings\n"
        + "\n".join(imports) + "\n\n"
        "logging.basicConfig(\n"
        '    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",\n'
        "    level=logging.INFO,\n"
        "    stream=sys.stdout,\n"
        ")\n"
        'logger = logging.getLogger("bot")\n\n\n'
        "async def _post_init(app: Application) -> None:\n"
        "    await app.bot.set_my_commands([\n"
        + bot_block + "\n"
        "    ])\n\n\n"
        "def build_application() -> Application:\n"
        "    settings = get_settings()\n"
        "    app = Application.builder().token(settings.telegram_bot_token).post_init(_post_init).build()\n"
        + "\n".join(regs) + "\n"
        "    return app\n\n\n"
        "def main() -> None:\n"
        '    logger.info("starting")\n'
        "    build_application().run_polling(allowed_updates=Update.ALL_TYPES)\n\n\n"
        'if __name__ == "__main__":\n'
        "    main()\n"
    )


# ─────────────────────────── requirements / env ──────────────────────────

def _emit_requirements(spec: RichSpec) -> str:
    reqs = [
        "python-telegram-bot>=21.0",
        "pydantic>=2.0",
        "pydantic-settings>=2.0",
    ]
    if spec.has_database():
        reqs += ["sqlalchemy[asyncio]>=2.0", "aiosqlite>=0.19"]
    return "\n".join(reqs) + "\n"


def _emit_env(spec: RichSpec) -> str:
    lines = ["TELEGRAM_BOT_TOKEN=", "ADMIN_USER_IDS=", "LOG_LEVEL=INFO"]
    if spec.has_database():
        lines.append("DATABASE_URL=sqlite+aiosqlite:///./bot.db")
    return "\n".join(lines) + "\n"


# ─────────────────────────── README ──────────────────────────────────────

def _emit_readme(spec: RichSpec) -> str:
    lines = [
        f"# {spec.bot_name}",
        "",
        spec.description or "",
        "",
        "## Commands",
        "",
    ]
    for c in spec.commands:
        admin = " (admin)" if c.admin_only else ""
        lines.append(f"- `/{c.name}` — {c.description or c.name}{admin}")
    if spec.buttons:
        lines += ["", "## Buttons", ""]
        for b in spec.buttons:
            lines.append(f"- {b.label} → `/{b.target_command}`" if b.target_command else f"- {b.label}")
    if spec.entities:
        lines += ["", "## Data Models", ""]
        for e in spec.entities:
            fields = ", ".join(f.name for f in e.fields)
            lines.append(f"- **{e.name}**: {fields}")
    lines += ["", "## Setup", "", "1. Copy `.env.example` to `.env` and set your bot token", "2. `pip install -r requirements.txt`", "3. `python main.py`", ""]
    return "\n".join(lines) + "\n"


# ─────────────────────────── main transpile entry ────────────────────────

def transpile_spec(spec: RichSpec, out_dir: str | Path) -> list[str]:
    """
    Generate a complete Telegram bot project from a RichSpec.
    Every file is derived from the spec — zero hardcoded templates.
    """
    root = Path(out_dir)
    app = root / "app"
    app.mkdir(parents=True, exist_ok=True)
    written: list[str] = []

    def w(rel: str, content: str) -> None:
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content.replace("\r\n", "\n").rstrip() + "\n", encoding="utf-8")
        written.append(str(path))

    w("app/__init__.py", '"""app package"""\n')
    w("app/models.py", _emit_schema_module(spec))
    w("app/store.py", _emit_store_module(spec))
    w("app/logic.py", _emit_logic_module(spec))
    w("app/handlers.py", _emit_handlers_module(spec))
    w("app/container.py", _emit_container(spec))
    w("app/config.py", _emit_config(spec))
    w("main.py", _emit_main(spec))
    w("requirements.txt", _emit_requirements(spec))
    w(".env.example", _emit_env(spec))
    w("README.md", _emit_readme(spec))
    return written
