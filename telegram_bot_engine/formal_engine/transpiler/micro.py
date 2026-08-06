"""
Micro-Transpiler — Statement by Statement from InferenceResult only.
No domain templates. No canned shop/ticket/admin packs.
Emits Python syntax that expresses inferred relations, operations, UI surface.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from ..inference.engine import InferenceResult


def _ident(name: str) -> str:
    s = re.sub(r"[^a-zA-Z0-9_]", "_", (name or "").strip())
    s = re.sub(r"_+", "_", s).strip("_")
    if not s or not re.match(r"[a-zA-Z]", s[0] if s else ""):
        s = "n_" + (s or "x")
    if s[0].isdigit():
        s = "n_" + s
    return s.lower()[:48]


def _cls(name: str) -> str:
    parts = [p for p in _ident(name).split("_") if p]
    return "".join(p.capitalize() for p in parts) or "Item"


def _py(s: Any) -> str:
    return repr(s)


# ── schema ──────────────────────────────────────────────────────────────

def _emit_schema_module(inf: InferenceResult) -> str:
    lines = [
        '"""Schemas derived from inferred entities only."""',
        "from __future__ import annotations",
        "from dataclasses import dataclass",
        "from typing import Any",
        "",
    ]
    schemas = inf.schemas or []
    if not schemas:
        lines += [
            "@dataclass",
            "class Record:",
            "    id: str = \"\"",
            "    user_id: int = 0",
            "    payload: str = \"\"",
            "",
            "    def to_dict(self) -> dict[str, Any]:",
            "        return {\"id\": self.id, \"user_id\": self.user_id, \"payload\": self.payload}",
            "",
        ]
        return "\n".join(lines) + "\n"

    for sch in schemas:
        cname = _cls(sch.table)
        lines.append("@dataclass")
        lines.append(f"class {cname}:")
        if not sch.columns:
            lines.append("    id: str = \"\"")
        else:
            for col, typ in sch.columns:
                ci = _ident(col)
                if typ == "int":
                    lines.append(f"    {ci}: int = 0")
                elif typ == "bool":
                    lines.append(f"    {ci}: bool = False")
                elif typ == "float":
                    lines.append(f"    {ci}: float = 0.0")
                else:
                    lines.append(f"    {ci}: str = \"\"")
        lines.append("")
        lines.append("    def to_dict(self) -> dict[str, Any]:")
        lines.append("        return {")
        for col, _t in sch.columns:
            lines.append(f"            {_py(_ident(col))}: self.{_ident(col)},")
        lines.append("        }")
        lines.append("")
    return "\n".join(lines) + "\n"


def _emit_store_module(inf: InferenceResult) -> str:
    """SQLite-backed stores — ready for real hosting (persistent)."""
    lines = [
        '"""SQLite stores derived from inferred schemas — hosting-ready."""',
        "from __future__ import annotations",
        "from typing import Any",
        "import json",
        "import sqlite3",
        "import uuid",
        "from pathlib import Path",
        "",
        "_DB_PATH = Path(__file__).resolve().parent.parent / 'data' / 'bot.db'",
        "",
        "def _conn() -> sqlite3.Connection:",
        "    _DB_PATH.parent.mkdir(parents=True, exist_ok=True)",
        "    c = sqlite3.connect(str(_DB_PATH))",
        "    c.row_factory = sqlite3.Row",
        "    return c",
        "",
        "class _BaseStore:",
        "    table: str = 'records'",
        "",
        "    def __init__(self) -> None:",
        "        with _conn() as c:",
        "            c.execute(",
        "                f'CREATE TABLE IF NOT EXISTS {self.table} ('",
        "                'id TEXT PRIMARY KEY, user_id INTEGER, payload TEXT, status TEXT, created_at TEXT'",
        "                ')'",
        "            )",
        "            c.commit()",
        "",
        "    async def create(self, **fields: Any) -> str:",
        "        oid = str(fields.get('id') or uuid.uuid4())",
        "        payload = dict(fields, id=oid)",
        "        uid = fields.get('user_id')",
        "        status = str(fields.get('status') or '')",
        "        with _conn() as c:",
        "            c.execute(",
        "                f\"INSERT OR REPLACE INTO {self.table} (id, user_id, payload, status, created_at) VALUES (?,?,?,?,datetime('now'))\",",
        "                (oid, uid, json.dumps(payload, ensure_ascii=False, default=str), status),",
        "            )",
        "            c.commit()",
        "        return oid",
        "",
        "    async def get(self, oid: str) -> Any:",
        "        with _conn() as c:",
        "            row = c.execute(f'SELECT payload FROM {self.table} WHERE id=?', (str(oid),)).fetchone()",
        "        return json.loads(row['payload']) if row else None",
        "",
        "    async def list_all(self) -> list[Any]:",
        "        with _conn() as c:",
        "            rows = c.execute(f'SELECT payload FROM {self.table} ORDER BY created_at DESC').fetchall()",
        "        return [json.loads(r['payload']) for r in rows]",
        "",
        "    async def list_by_user(self, user_id: int) -> list[Any]:",
        "        with _conn() as c:",
        "            rows = c.execute(",
        "                f'SELECT payload FROM {self.table} WHERE user_id=? ORDER BY created_at DESC',",
        "                (user_id,),",
        "            ).fetchall()",
        "        return [json.loads(r['payload']) for r in rows]",
        "",
        "    async def update_status(self, oid: str, status: str) -> bool:",
        "        with _conn() as c:",
        "            row = c.execute(f'SELECT payload FROM {self.table} WHERE id=?', (str(oid),)).fetchone()",
        "            if not row:",
        "                return False",
        "            data = json.loads(row['payload'])",
        "            data['status'] = status",
        "            c.execute(",
        "                f'UPDATE {self.table} SET payload=?, status=? WHERE id=?',",
        "                (json.dumps(data, ensure_ascii=False, default=str), status, str(oid)),",
        "            )",
        "            c.commit()",
        "        return True",
        "",
    ]
    schemas = inf.schemas or []
    if not schemas:
        lines += [
            "class RecordStore(_BaseStore):",
            "    table = 'records'",
            "",
        ]
        return "\n".join(lines) + "\n"

    for sch in schemas:
        cname = _cls(sch.table)
        tname = "".join(ch if ch.isalnum() else "_" for ch in sch.table.lower())[:40] or "records"
        lines.append(f"class {cname}Store(_BaseStore):")
        lines.append(f"    table = {_py(tname)}")
        lines.append("")
    return "\n".join(lines) + "\n"



def _emit_logic_module(inf: InferenceResult) -> str:
    lines = [
        '"""Logic derived from inferred decisions, loops, actions, steps, rules."""',
        "from __future__ import annotations",
        "from typing import Any",
        "",
    ]

    # ── deep rules engine (statement-by-statement from extracted rules) ──
    rules = list(getattr(inf, "rules", None) or [])
    lines.append("def _as_number(v: Any, default: float = 0.0) -> float:")
    lines.append("    try:")
    lines.append("        return float(v)")
    lines.append("    except Exception:")
    lines.append("        return default")
    lines.append("")
    lines.append("def _check_condition(cond: dict[str, Any], ctx: dict[str, Any]) -> bool:")
    lines.append("    left = str(cond.get(\"left\") or \"\")")
    lines.append("    op = str(cond.get(\"op\") or \"eq\")")
    lines.append("    right = cond.get(\"right\")")
    lines.append("    val = ctx.get(left)")
    lines.append("    if val is None and left in (\"choice\", \"signal\"):")
    lines.append("        val = ctx.get(\"choice\") or ctx.get(\"text\") or \"\"")
    lines.append("    if op == \"truthy\":")
    lines.append("        return bool(val) and str(val).lower() not in (\"0\", \"false\", \"no\", \"\")")
    lines.append("    if op == \"contains\":")
    lines.append("        sv, sr = str(val or \"\"), str(right or \"\")")
    lines.append("        if not sv or not sr:")
    lines.append("            return False")
    lines.append("        return sr in sv or sv in sr")
    lines.append("    if op in (\"gt\", \"gte\", \"lt\", \"lte\"):")
    lines.append("        if val is None or str(val).strip() == \"\":")
    lines.append("            return False")
    lines.append("        a = _as_number(val)")
    lines.append("        if isinstance(right, str) and str(right).startswith(\"@\"):")
    lines.append("            right = ctx.get(str(right)[1:])")
    lines.append("            if right is None or str(right).strip() == \"\":")
    lines.append("                return False")
    lines.append("        b = _as_number(right)")
    lines.append("        if op == \"gt\":")
    lines.append("            return a > b")
    lines.append("        if op == \"gte\":")
    lines.append("            return a >= b")
    lines.append("        if op == \"lt\":")
    lines.append("            return a < b")
    lines.append("        return a <= b")
    lines.append("    if op == \"ne\":")
    lines.append("        return str(val) != str(right)")
    lines.append("    if isinstance(val, bool):")
    lines.append("        truthy_r = str(right).lower() in (\"1\", \"true\", \"yes\", \"ok\")")
    lines.append("        falsy_r = str(right).lower() in (\"0\", \"false\", \"no\", \"\")")
    lines.append("        if truthy_r:")
    lines.append("            return val is True")
    lines.append("        if falsy_r:")
    lines.append("            return val is False")

    lines.append("    # eq default — exact / contains (reject empty val unless right empty)")
    lines.append("    sv, sr = str(val if val is not None else \"\"), str(right if right is not None else \"\")")
    lines.append("    if not sv and sr:")
    lines.append("        return False")
    lines.append("    if sv == sr:")
    lines.append("        return True")
    lines.append("    if sv and sr and (sr in sv or sv in sr):")
    lines.append("        return True")
    lines.append("    return sv.replace(\"_\", \"\") == sr.replace(\"_\", \"\")")
    lines.append("")
    lines.append("def _apply_effect(effect: dict[str, Any], ctx: dict[str, Any]) -> dict[str, Any]:")
    lines.append("    kind = str(effect.get(\"kind\") or \"\")")
    lines.append("    target = str(effect.get(\"target\") or \"\")")
    lines.append("    value = effect.get(\"value\")")
    lines.append("    out = dict(ctx)")
    lines.append("    msgs = list(out.get(\"_messages\") or [])")
    lines.append("    if kind == \"set\":")
    lines.append("        out[target] = value if value != \"computed\" else out.get(target, 0)")
    lines.append("    elif kind == \"enable\":")
    lines.append("        out[f\"enable_{target}\"] = True")
    lines.append("        msgs.append(f\"enabled:{target}\")")
    lines.append("    elif kind == \"reply\":")
    lines.append("        msgs.append(str(value or target or \"ok\"))")
    lines.append("    elif kind == \"goto\":")
    lines.append("        out[\"_goto\"] = target")
    lines.append("    elif kind == \"create\":")
    lines.append("        out[\"_create\"] = target")
    lines.append("        out[\"_create_payload\"] = {k: v for k, v in out.items() if not str(k).startswith(\"_\")}")
    lines.append("        msgs.append(f\"create:{target}\")")
    lines.append("    elif kind == \"call\":")
    lines.append("        out[\"_call\"] = target")
    lines.append("        msgs.append(f\"call:{target}\")")
    lines.append("    elif kind == \"accumulate\":")
    lines.append("        weight = 1.0")
    lines.append("        src_key = str(value) or \"answers\"")
    lines.append("        if \"*\" in src_key:")
    lines.append("            base, _, w = src_key.partition(\"*\")")
    lines.append("            src_key = base or \"answers\"")
    lines.append("            weight = _as_number(w, 1.0)")
    lines.append("        src = out.get(src_key) or out.get(\"answers\") or out.get(\"collected\") or []")
    lines.append("        if isinstance(src, dict):")
    lines.append("            src = list(src.values())")
    lines.append("        total = 0.0")
    lines.append("        n = 0")
    lines.append("        for item in list(src or []):")
    lines.append("            total += _as_number(item) * weight")
    lines.append("            n += 1")
    lines.append("        out[target or \"score\"] = int(total)")
    lines.append("        out[f\"{target or \"score\"}_count\"] = n")
    lines.append("        msgs.append(f\"{target or \"score\"}={out[target or \"score\"]}\")")
    lines.append("    out[\"_messages\"] = msgs")
    lines.append("    return out")
    lines.append("")

    # embed rules as data
    rules_data = []
    for r in rules:
        rules_data.append({
            "name": r.name,
            "kind": r.kind,
            "conditions": [{"left": c.left, "op": c.op, "right": c.right, "raw": getattr(c, "raw", "") or ""} for c in r.conditions],
            "effects": [{"kind": e.kind, "target": e.target, "value": e.value} for e in r.effects],
        })
    lines.append(f"_RULES = {_py(rules_data)}")
    lines.append("")
    lines.append("def apply_rules(ctx: dict[str, Any] | None = None) -> dict[str, Any]:")
    lines.append("    \"\"\"Evaluate all inferred rules against context; return updated context.\"\"\"")
    lines.append("    out = dict(ctx or {})")
    lines.append("    matched: list[str] = []")
    lines.append("    for rule in _RULES:")
    lines.append("        conds = list(rule.get(\"conditions\") or [])")
    lines.append("        ok = True")
    lines.append("        if conds:")
    lines.append("            mode_any = any(str(c.get(\"raw\") or \"\").startswith(\"ANY|\") for c in conds)")
    lines.append("            if mode_any:")
    lines.append("                ok = any(_check_condition(c, out) for c in conds)")
    lines.append("            else:")
    lines.append("                ok = all(_check_condition(c, out) for c in conds)")
    lines.append("        # compute runs only with answers list")
    lines.append("        if rule.get(\"kind\") == \"compute\":")
    lines.append("            ok = isinstance(out.get(\"answers\"), (list, tuple)) and len(list(out.get(\"answers\") or [])) > 0")
    lines.append("        if not ok:")
    lines.append("            continue")
    lines.append("        matched.append(str(rule.get(\"name\") or \"\"))")
    lines.append("        for eff in list(rule.get(\"effects\") or []):")
    lines.append("            out = _apply_effect(eff, out)")
    lines.append("    out[\"_matched_rules\"] = matched")
    lines.append("    return out")
    lines.append("")

    for d in inf.decisions:
        fname = _ident(d.name)
        lines.append(f"def {fname}(discriminant: Any) -> str:")
        lines.append(f"    \"\"\"Decision from inference: {d.name}.\"\"\"")
        if not d.branches:
            lines.append("    return \"default\"")
        else:
            for i, br in enumerate(d.branches):
                label = str(br.get("label") or f"b{i}")
                target = str(br.get("target") or f"path_{i}")
                kw = "if" if i == 0 else "elif"
                lines.append(f"    {kw} str(discriminant) == {_py(label)} or {_py(label)} in str(discriminant):")
                lines.append(f"        return {_py(target)}")
            lines.append("    return \"default\"")
        lines.append("")

    for lp in inf.loops:
        fname = _ident(lp.name)
        lines.append(f"def {fname}(items: list[Any], handler=None) -> list[Any]:")
        lines.append(f"    \"\"\"Loop from inference over {lp.iterable}.\"\"\"")
        lines.append("    result: list[Any] = []")
        lines.append("    for item in list(items or []):")
        lines.append("        if handler is not None:")
        lines.append("            item = handler(item)")
        lines.append("        result.append(item)")
        lines.append("    return result")
        lines.append("")

    seen_actions: set[str] = set()
    for aname in inf.actions:
        fname = _ident(aname)
        if fname in seen_actions:
            continue
        seen_actions.add(fname)
        lines.append(f"async def {fname}(store: Any = None, user_id: int = 0, payload: dict | None = None, args: list | None = None) -> str:")
        lines.append(f"    \"\"\"Action {aname} from relation + rules.\"\"\"")
        lines.append("    payload = dict(payload or {})")
        lines.append("    args = list(args or [])")
        lines.append("    payload.setdefault(\"user_id\", user_id)")
        lines.append("    # run deep rules on payload context")
        lines.append("    ctx = apply_rules(payload)")
        lines.append("    messages = list(ctx.get(\"_messages\") or [])")
        lines.append("    if store is None:")
        lines.append("        return \" | \".join(messages) if messages else \"ok\"")
        lines.append("    if args and hasattr(store, \"get\"):")
        lines.append("        row = await store.get(str(args[0]))")
        lines.append("        return str(row) if row is not None else \"not_found\"")
        lines.append("    # create effect from rules")
        lines.append("    if ctx.get(\"_create\") and hasattr(store, \"create\"):")
        lines.append("        pl = dict(ctx.get(\"_create_payload\") or payload)")
        lines.append("        pl.setdefault(\"user_id\", user_id)")
        lines.append("        oid = await store.create(**{k: v for k, v in pl.items() if not str(k).startswith(\"_\")})")
        lines.append("        messages.append(f\"ok:{oid}\")")
        lines.append("        return \" | \".join(messages)")
        lines.append("    if hasattr(store, \"list_by_user\") and user_id and not any(k not in (\"user_id\",) and not str(k).startswith(\"_\") for k in payload.keys()):")
        lines.append("        rows = await store.list_by_user(user_id)")
        lines.append("        if rows:")
        lines.append("            return \"\\n\".join(str(getattr(r, \"to_dict\", lambda: r)()) for r in rows[:30])")
        lines.append("    if hasattr(store, \"create\") and any(k not in (\"user_id\",) and not str(k).startswith(\"_\") for k in payload.keys()):")
        lines.append("        oid = await store.create(**{k: v for k, v in payload.items() if not str(k).startswith(\"_\")})")
        lines.append("        messages.append(f\"ok:{oid}\")")
        lines.append("        return \" | \".join(messages) if messages else f\"ok:{oid}\"")
        lines.append("    return \" | \".join(messages) if messages else \"ok\"")
        lines.append("")

    for step in inf.compute_steps:
        fname = _ident(step["name"])
        label = step.get("label") or step["name"]
        lines.append(f"def {fname}(context: dict[str, Any]) -> dict[str, Any]:")
        lines.append(f"    \"\"\"{str(label)[:80]}\"\"\"")
        lines.append("    ctx = dict(context or {})")
        lines.append(f"    ctx[{_py('last_step')}] = {_py(step['name'])}")
        lines.append("    return apply_rules(ctx)")
        lines.append("")

    if len(lines) <= 8:
        lines += ["def noop(context: dict[str, Any] | None = None) -> dict[str, Any]:", "    return dict(context or {})", ""]
    return "\n".join(lines) + "\n"



def _emit_handlers_module(inf: InferenceResult) -> str:
    """Handlers from inferred commands, buttons, steps — no domain packs."""
    commands = list(inf.commands or [])
    buttons = list(inf.buttons or [])
    steps = list(inf.compute_steps or [])
    schemas = list(inf.schemas or [])

    # stable step ids already step_N from extractor
    step_ids = [_ident(s["name"]) for s in steps]
    step_labels = { _ident(s["name"]): str(s.get("label") or s["name"])[:200] for s in steps }
    first_step = step_ids[0] if step_ids else None
    wizards = list(getattr(inf, "wizards", None) or [])
    wizard_by_cmd = {str(w.get("command") or w.get("id")): w for w in wizards}

    # map command → store name by stem overlap with schemas
    schema_names = [_ident(s.table) for s in schemas]
    action_names = [_ident(a) for a in (inf.actions or [])]

    def store_for_cmd(cmd: str) -> str | None:
        c = cmd.lower().replace("-", "_")
        soft: list[tuple[tuple[str, ...], tuple[str, ...]]] = [
            (("enroll", "my_course", "my_courses", "progress", "score", "quiz"), ("enrollment", "enrolment", "registration")),
            (("register", "student", "ban", "user"), ("student", "user", "member")),
            (("order", "cart"), ("order", "purchase")),
            (("ticket", "complaint"), ("ticket", "issue")),
            (("product", "item", "catalog"), ("product", "item")),
            (("book", "appoint"), ("booking", "reservation", "appointment")),
            # bare course list last so my_courses does not win as course
            (("courses", "course_list", "catalog"), ("course", "class", "subject")),
        ]
        for triggers, stems in soft:
            if any(t in c for t in triggers):
                for sn in schema_names:
                    if any(st in sn for st in stems):
                        return sn
        # exact-ish course command
        if c in ("course", "courses") or c.endswith("_courses"):
            for sn in schema_names:
                if "course" in sn and "enroll" not in sn:
                    return sn
        for sn in schema_names:
            if sn in c or c in sn or c.rstrip("s") == sn or sn.rstrip("s") == c:
                return sn
        return schema_names[0] if len(schema_names) == 1 else None

    def action_for_cmd(cmd: str) -> str | None:
        c = cmd.lower()
        for an in action_names:
            if c in an or an.endswith(c) or c in an.replace("manage", ""):
                return an
        return action_names[0] if action_names else None

    def cmd_kind(cmd: str) -> str:
        c = cmd.lower()
        if c in ("stats", "statistics", "dashboard", "charts") or c.endswith("_stats") or c.endswith("_charts"):
            return "stats"
        if c.startswith("my_") or c in ("progress", "score", "history", "profile", "wallet", "settings"):
            return "mine"
        if c in ("courses", "catalog", "users", "tickets", "reports", "logs", "audit_log",
                 "error_logs", "devices", "sessions", "permissions", "subscription",
                 "subscriptions", "notifications", "reviews", "backup") or any(
            x in c for x in ("list", "products", "items", "tickets", "orders", "users",
                             "reports", "logs", "devices", "sessions", "permissions",
                             "notifications", "reviews", "subscriptions")):
            return "list"
        if any(x in c for x in ("ban", "delete", "remove", "cancel", "drop", "block")):
            return "mutate"
        if any(x in c for x in ("broadcast", "notify", "notification", "alert")):
            return "broadcast"
        return "generic"

    lines: list[str] = [
        '"""Handlers from inferred commands/buttons/steps only."""',
        "from __future__ import annotations",
        "from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup",
        "from telegram.ext import ContextTypes",
        "from app import logic",
        "from app.container import get_container",
        "",
        "",
    ]
    _wiz = list(getattr(inf, "wizards", None) or [])
    lines.append("FLOWS: dict[str, list[dict[str, str]]] = {")
    for w in _wiz:
        wid = str(w.get("id") or w.get("command") or "flow")
        lines.append(f"    {_py(wid)}: [")
        for st in (w.get("steps") or []):
            lines.append(
                "        {\"key\": %s, \"prompt\": %s}," % (_py(st.get("key")), _py(st.get("prompt")))
            )
        lines.append("    ],")
    lines.append("}")
    lines.append("FLOW_ENTITY: dict[str, str] = {")
    for w in _wiz:
        wid = str(w.get("id") or w.get("command") or "flow")
        lines.append(f"    {_py(wid)}: {_py(w.get('entity') or 'record')},")
    lines.append("}")
    lines.append("FLOW_KIND: dict[str, str] = {")
    for w in _wiz:
        wid = str(w.get("id") or w.get("command") or "flow")
        lines.append(f"    {_py(wid)}: {_py(w.get('kind') or 'collect')},")
    lines.append("}")
    lines.append("")
    lines.append("")
    lines.append("async def _start_flow(message, context, flow_id: str) -> None:")
    lines.append("    steps = FLOWS.get(flow_id) or []")
    lines.append("    if not steps:")
    lines.append("        await message.reply_text('flow empty')")
    lines.append("        return")
    lines.append("    context.user_data.clear()")
    lines.append("    context.user_data['flow'] = flow_id")
    lines.append("    context.user_data['step'] = 0")
    lines.append("    context.user_data['data'] = {}")
    lines.append("    context.user_data['state'] = f'flow:{flow_id}:0'")
    lines.append("    await message.reply_text(steps[0]['prompt'])")
    lines.append("")
    lines.append("")

    # Keyboard: prefer user buttons; else structural buttons from real commands
    # (not a domain pack — each button is 1:1 with an extracted command).
    kb_items: list[tuple[str, str]] = []
    if buttons:
        for b in buttons:
            kb_items.append((b.label, b.callback_id or _ident(b.label)))
    else:
        for c in commands:
            if c.name in ("start", "help"):
                continue
            label = (c.description or c.name).strip()[:40] or c.name
            kb_items.append((label, f"cmd:{c.name}"))

    # button callback_id → command name (for routing)
    btn_to_cmd: dict[str, str] = {}
    for label, cb in kb_items:
        # direct cmd:name
        if cb.startswith("cmd:"):
            btn_to_cmd[cb] = cb[4:]
            continue
        # match label/cb to a command name or description
        for c in commands:
            if c.name in ("start", "help"):
                continue
            if cb == c.name or cb == f"cmd_{c.name}" or _ident(label) == c.name:
                btn_to_cmd[cb] = c.name
                break
            desc = (c.description or "").strip()
            if desc and (desc == label or desc in label or label in desc):
                btn_to_cmd[cb] = c.name
                break
            if any(tok in label for tok in (c.name, c.name.replace("_", " ")) if len(tok) > 2):
                btn_to_cmd[cb] = c.name
                break

    lines.append("BUTTON_TO_CMD: dict[str, str] = {")
    for cb, cn in btn_to_cmd.items():
        lines.append(f"    {_py(cb)}: {_py(cn)},")
    lines.append("}")
    lines.append("")
    lines.append("")

    lines.append("def main_keyboard() -> InlineKeyboardMarkup | None:")
    if kb_items:
        lines.append("    rows = []")
        row: list[str] = []
        for i, (label, cb) in enumerate(kb_items):
            row.append(
                f"InlineKeyboardButton({_py(label)}, callback_data={_py(cb)})"
            )
            if len(row) == 2 or i == len(kb_items) - 1:
                lines.append(f"    rows.append([{', '.join(row)}])")
                row = []
        lines.append("    return InlineKeyboardMarkup(rows)")
    else:
        lines.append("    return None")
    lines.append("")
    lines.append("")

    # start — welcome + short command map
    start_bits = ["مرحباً بك 👋"]
    for c in commands[:12]:
        start_bits.append(f"/{c.name} — {c.description or c.name}")
    start_msg = "\n".join(start_bits)
    lines.append("async def start_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:")
    lines.append("    message = update.effective_message")
    lines.append("    if message is None:")
    lines.append("        return")
    lines.append("    context.user_data.clear()")
    if first_step:
        lines.append(f"    context.user_data[\"state\"] = {_py(first_step)}")
    if kb_items:
        lines.append("    kb = main_keyboard()")
        lines.append(f"    await message.reply_text({_py(start_msg)}, reply_markup=kb)")
    else:
        lines.append(f"    await message.reply_text({_py(start_msg)})")
    lines.append("")
    lines.append("")

    # help
    lines.append("async def help_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:")
    lines.append("    message = update.effective_message")
    lines.append("    if message is None:")
    lines.append("        return")
    help_lines = [f"/{c.name} — {c.description}" for c in commands]
    help_text = "\n".join(help_lines) if help_lines else "help"
    lines.append(f"    await message.reply_text({_py(help_text)})")
    lines.append("")
    lines.append("")

    # one handler per inferred command except start/help
    for cmd in commands:
        if cmd.name in ("start", "help"):
            continue
        fn = _ident(cmd.name) + "_handler"
        store = store_for_cmd(cmd.name)
        action = action_for_cmd(cmd.name)
        lines.append(f"async def {fn}(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:")
        lines.append("    message = update.effective_message")
        lines.append("    if message is None:")
        lines.append("        return")
        lines.append("    user = update.effective_user")
        lines.append("    uid = user.id if user else 0")
        if cmd.name in wizard_by_cmd:
            lines.append(f"    await _start_flow(message, context, {_py(cmd.name)})")
            lines.append("    return")
            lines.append("")
            lines.append("")
            continue
        if cmd.admin_only:
            lines.append("    from app.config import get_settings")
            lines.append("    settings = get_settings()")
            lines.append("    admins = set()")
            lines.append("    raw = getattr(settings, \"admin_user_ids\", \"\") or \"\"")
            lines.append("    for part in str(raw).split(\",\"):")
            lines.append("        part = part.strip()")
            lines.append("        if part.isdigit():")
            lines.append("            admins.add(int(part))")
            lines.append("    if admins and uid not in admins:")
            lines.append("        await message.reply_text(\"admin_only\")")
            lines.append("        return")
        lines.append("    args = []")
        lines.append("    if message.text and \" \" in message.text:")
        lines.append("        args = message.text.split()[1:]")
        lines.append("    container = get_container()")
        if store:
            lines.append(f"    store = getattr(container, {_py(store)}, None)")
        else:
            lines.append("    store = getattr(container, \"primary_store\", None)")
        cn = cmd.name.lower()
        kind = cmd_kind(cmd.name)
        lines.append("    payload: dict = {\"user_id\": uid, \"intent\": %s}" % _py(cn))
        lines.append("    if args:")
        lines.append("        payload[\"args\"] = args")
        lines.append("        payload[\"text\"] = \" \".join(args)")
        # intent soft mapping for rule engine
        if any(x in cn for x in ("pay", "invoice")):
            lines.append("    payload[\"paid\"] = True")
            lines.append("    payload[\"intent\"] = \"pay\"")
        elif any(x in cn for x in ("ban", "block")):
            lines.append("    payload[\"banned\"] = True")
            lines.append("    payload[\"intent\"] = \"ban\"")
        lines.append("    ruled = logic.apply_rules(payload)")
        lines.append("    msgs = list(ruled.get(\"_messages\") or [])")
        # --- behavioral paths by command kind ---
        if kind == "list":
            lines.append("    rows = []")
            lines.append("    if store is not None and hasattr(store, \"list_all\"):")
            lines.append("        try:")
            lines.append("            rows = await store.list_all()")
            lines.append("        except Exception as exc:")
            lines.append("            msgs.append(f\"list_error:{exc}\")")
            lines.append("    if rows:")
            lines.append("        lines_out = []")
            lines.append("        for i, row in enumerate(rows[:20], 1):")
            lines.append("            if isinstance(row, dict):")
            lines.append("                summary = \" | \".join(f\"{k}={v}\" for k, v in list(row.items())[:6])")
            lines.append("            else:")
            lines.append("                summary = str(row)[:120]")
            lines.append("            lines_out.append(f\"{i}. {summary}\")")
            lines.append("        await message.reply_text(\"\\n\".join(lines_out))")
            lines.append("    elif not msgs:")
            lines.append(f"        await message.reply_text({_py((cmd.description or cmd.name) + ' — لا توجد عناصر بعد')})")
        elif kind == "mine":
            lines.append("    rows = []")
            lines.append("    if store is not None and hasattr(store, \"list_by_user\"):")
            lines.append("        try:")
            lines.append("            rows = await store.list_by_user(uid)")
            lines.append("        except Exception as exc:")
            lines.append("            msgs.append(f\"mine_error:{exc}\")")
            lines.append("    if rows:")
            lines.append("        lines_out = []")
            lines.append("        for i, row in enumerate(rows[:20], 1):")
            lines.append("            if isinstance(row, dict):")
            lines.append("                summary = \" | \".join(f\"{k}={v}\" for k, v in list(row.items())[:6])")
            lines.append("            else:")
            lines.append("                summary = str(row)[:120]")
            lines.append("            lines_out.append(f\"{i}. {summary}\")")
            lines.append("        await message.reply_text(\"\\n\".join(lines_out))")
            lines.append("    elif not msgs:")
            lines.append(f"        await message.reply_text({_py((cmd.description or 'لا توجد بيانات خاصة بك بعد'))})")
        elif kind == "stats":
            lines.append("    count = 0")
            lines.append("    if store is not None and hasattr(store, \"list_all\"):")
            lines.append("        try:")
            lines.append("            count = len(await store.list_all())")
            lines.append("        except Exception:")
            lines.append("            count = 0")
            lines.append("    await message.reply_text(f\"إحصائيات: {count} سجل\")")
        elif kind == "mutate":
            lines.append("    target = args[0] if args else None")
            lines.append("    if target and store is not None and hasattr(store, \"update_status\"):")
            lines.append("        try:")
            lines.append("            ok = await store.update_status(str(target), \"banned\" if \"ban\" in %s else \"updated\")" % _py(cn))
            lines.append("            msgs.append(\"done\" if ok else \"not_found\")")
            lines.append("        except Exception as exc:")
            lines.append("            msgs.append(f\"mutate_error:{exc}\")")
            lines.append("    if msgs:")
            lines.append("        await message.reply_text(\" | \".join(str(m) for m in msgs[:5]))")
            lines.append("    else:")
            lines.append(f"        await message.reply_text({_py((cmd.description or cmd.name) + ' — أرسل المعرّف كوسيط')})")
        elif kind == "broadcast":
            lines.append(f"    await message.reply_text({_py('أرسل نص الرسالة بعد الأمر: /' + cmd.name + ' النص')})")
        else:
            # generic: rules + optional action + meaningful fallback
            lines.append("    if msgs:")
            lines.append("        await message.reply_text(\" | \".join(str(m) for m in msgs[:5]))")
            if action:
                lines.append(f"    result = await logic.{action}(store=store, user_id=uid, payload=ruled, args=args)")
                lines.append("    if result and result not in (\"ok\",):")
                lines.append("        await message.reply_text(str(result))")
            # meaningful fallback: try to show record count from store before echoing desc
            lines.append("    if not msgs:")
            lines.append("        _shown = False")
            lines.append("        if store is not None and hasattr(store, \"list_all\"):")
            lines.append("            try:")
            lines.append("                _rows = await store.list_all()")
            lines.append("                _n = len(_rows) if _rows else 0")
            lines.append(f"                await message.reply_text(f\"{{{_py(cmd.description or cmd.name)}}} — عدد السجلات: {{_n}}\")")
            lines.append("                _shown = True")
            lines.append("            except Exception:")
            lines.append("                pass")
            lines.append("        if not _shown:")
            lines.append(f"            await message.reply_text({_py((cmd.description or cmd.name) + ' — جرّب إرسال بيانات بعد الأمر لمزيد من التفاصيل')})")
        if buttons:
            lines.append("    kb = main_keyboard()")
            lines.append("    if kb is not None and %s not in (\"list\", \"mine\", \"stats\"):" % _py(kind))
            lines.append(f"        await message.reply_text({_py('—')}, reply_markup=kb)")
        lines.append("")
        lines.append("")

    # message handler — fixed state machine using same step ids
        # Multi-screen message handler — wizard steps then rules
    lines.append("async def message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:")
    lines.append("    message = update.effective_message")
    lines.append("    if message is None:")
    lines.append("        return")
    lines.append("    ud = context.user_data")
    lines.append("    text = (message.text or \"\").strip()")
    lines.append("    if message.photo:")
    lines.append("        text = message.photo[-1].file_id")
    lines.append("    elif message.document:")
    lines.append("        text = message.document.file_id")
    lines.append("    flow_id = ud.get(\"flow\")")
    lines.append("    steps = FLOWS.get(str(flow_id) or \"\") or []")
    lines.append("    if flow_id and steps:")
    lines.append("        step_i = int(ud.get(\"step\") or 0)")
    lines.append("        data = dict(ud.get(\"data\") or {})")
    lines.append("        if step_i < 0 or step_i >= len(steps):")
    lines.append("            ud.clear()")
    lines.append("            await message.reply_text(\"انتهت الشاشات — /start\")")
    lines.append("            return")
    lines.append("        key = steps[step_i][\"key\"]")
    lines.append("        data[key] = text")
    lines.append("        # numeric helpers")
    lines.append("        if str(text).replace('.', '', 1).isdigit():")
    lines.append("            try:")
    lines.append("                data[key] = float(text) if '.' in text else int(text)")
    lines.append("            except Exception:")
    lines.append("                pass")
    lines.append("        ud[\"data\"] = data")
    lines.append("        step_i += 1")
    lines.append("        if step_i < len(steps):")
    lines.append("            ud[\"step\"] = step_i")
    lines.append("            ud[\"state\"] = f\"flow:{flow_id}:{step_i}\"")
    lines.append("            await message.reply_text(steps[step_i][\"prompt\"])")
    lines.append("            return")
    lines.append("        # completed wizard — apply rules + create entity")
    lines.append("        user = update.effective_user")
    lines.append("        uid = user.id if user else 0")
    lines.append("        payload = dict(data)")
    lines.append("        payload[\"user_id\"] = uid")
    lines.append("        payload[\"intent\"] = str(flow_id)")
    lines.append("        # sensible defaults for rule engine")
    lines.append("        if \"weight\" in payload and payload.get(\"weight\"):")
    lines.append("            pass")
    lines.append("        ruled = logic.apply_rules(payload)")
    lines.append("        msgs = list(ruled.get(\"_messages\") or [])")
    lines.append("        entity = FLOW_ENTITY.get(str(flow_id)) or ruled.get(\"_create\")")
    lines.append("        flow_kind = FLOW_KIND.get(str(flow_id)) or \"collect\"")
    lines.append("        container = get_container()")
    lines.append("        store = getattr(container, \"primary_store\", None)")
    lines.append("        if flow_kind == \"lookup\":")
    lines.append("            qid = str(ruled.get(\"id\") or ruled.get(\"text\") or \"\").strip()")
    lines.append("            row = None")
    lines.append("            if store is not None and qid and hasattr(store, \"get\"):")
    lines.append("                try:")
    lines.append("                    row = await store.get(qid)")
    lines.append("                except Exception as exc:")
    lines.append("                    msgs.append(f\"lookup_error:{exc}\")")
    lines.append("            if row:")
    lines.append("                if isinstance(row, dict):")
    lines.append("                    summary = \" | \".join(f\"{k}={v}\" for k, v in list(row.items())[:8])")
    lines.append("                else:")
    lines.append("                    summary = str(row)[:200]")
    lines.append("                msgs.append(summary)")
    lines.append("            elif not msgs:")
    lines.append("                msgs.append(f\"لم يتم العثور على {entity or 'سجل'}: {qid}\")")
    lines.append("        elif store is not None and hasattr(store, \"create\"):")
    lines.append("            try:")
    lines.append("                oid = await store.create(**{k: v for k, v in ruled.items() if not str(k).startswith(\"_\")})")
    lines.append("                msgs.append(f\"saved:{entity or 'record'}:{oid}\")")
    lines.append("            except Exception as exc:")
    lines.append("                msgs.append(f\"save_error:{exc}\")")
    lines.append("        ud.clear()")
    lines.append("        summary = \" | \".join(str(m) for m in msgs[:6]) if msgs else f\"تم — {entity or flow_id}\"")
    lines.append("        kb = main_keyboard()")
    lines.append("        if kb is not None:")
    lines.append("            await message.reply_text(summary, reply_markup=kb)")
    lines.append("        else:")
    lines.append("            await message.reply_text(summary)")
    lines.append("        return")
    lines.append("    # legacy single-state path")
    lines.append("    state = ud.get(\"state\")")
    lines.append("    if not state:")
    lines.append("        kb = main_keyboard()")
    lines.append("        if kb is not None:")
    lines.append("            await message.reply_text(\"استخدم /start أو اختر أمراً\", reply_markup=kb)")
    lines.append("        else:")
    lines.append("            await message.reply_text(\"استخدم /start\")")
    lines.append("        return")
    lines.append("    collected = dict(ud.get(\"collected\") or {})")
    lines.append("    collected[str(state)] = text")
    lines.append("    collected[\"text\"] = text")
    lines.append("    if str(text).replace('.', '', 1).isdigit():")
    lines.append("        collected.setdefault(\"progress\", int(float(text)))")
    lines.append("        collected.setdefault(\"score\", int(float(text)))")
    lines.append("    ruled = logic.apply_rules(collected)")
    lines.append("    ud[\"collected\"] = ruled")
    lines.append("    if ruled.get(\"_messages\"):")
    lines.append("        await message.reply_text(\" | \".join(str(m) for m in ruled[\"_messages\"][:5]))")
    if step_ids:
        lines.append(f"    order = {_py(step_ids)}")
        lines.append("    try:")
        lines.append("        idx = order.index(str(state))")
        lines.append("        if idx + 1 < len(order):")
        lines.append("            nxt = order[idx + 1]")
        lines.append("            ud[\"state\"] = nxt")
        lines.append(f"            labels = {_py(step_labels)}")
        lines.append("            await message.reply_text(labels.get(nxt, nxt))")
        lines.append("        else:")
        lines.append("            ud[\"state\"] = None")
        lines.append("            await message.reply_text(\"اكتملت الخطوات\")")
        lines.append("    except ValueError:")
        lines.append("        pass")
    lines.append("")
    lines.append("")

    # callback handler
    # callback handler — uses inferred decision + button targets
    lines.append("async def callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:")
    lines.append("    query = update.callback_query")
    lines.append("    if query is None:")
    lines.append("        return")
    lines.append("    await query.answer()")
    lines.append("    data = query.data or \"\"")
    lines.append("    context.user_data[\"choice\"] = data")
    lines.append("    # Route button → command/flow (structural mapping, no domain packs)")
    lines.append("    target_cmd = BUTTON_TO_CMD.get(data) or \"\"")
    lines.append("    if not target_cmd and data.startswith(\"cmd:\"):")
    lines.append("        target_cmd = data[4:]")
    lines.append("    if target_cmd and target_cmd in FLOWS and FLOWS[target_cmd]:")
    lines.append("        if query.message is not None:")
    lines.append("            await _start_flow(query.message, context, target_cmd)")
    lines.append("        return")
    lines.append("    if target_cmd:")
    lines.append("        # Non-wizard command: run its logic inline so buttons are functional")
    lines.append("        ruled = logic.apply_rules({\"choice\": data, \"text\": data, \"intent\": target_cmd, **dict(context.user_data.get(\"collected\") or {})})")
    lines.append("        context.user_data[\"collected\"] = ruled")
    lines.append("        msgs = list(ruled.get(\"_messages\") or [])")
    lines.append("        if msgs:")
    lines.append("            msg = \" | \".join(str(m) for m in msgs[:5])")
    lines.append("        else:")
    lines.append("            # try to show a count from the store for a meaningful button response")
    lines.append("            msg = f\"\u062a\u0645 \u062a\u0641\u0639\u064a\u0644 /{target_cmd}\"")
    lines.append("            try:")
    lines.append("                _c = get_container()")
    lines.append("                _s = getattr(_c, \"primary_store\", None)")
    lines.append("                if _s is not None and hasattr(_s, \"list_all\"):")
    lines.append("                    _rows = await _s.list_all()")
    lines.append("                    msg = f\"/{target_cmd} \u2014 \u0639\u062f\u062f \u0627\u0644\u0633\u062c\u0644\u0627\u062a: {len(_rows) if _rows else 0}\"")
    lines.append("            except Exception:")
    lines.append("                pass")
    lines.append("        if query.message is not None:")
    lines.append("            await query.edit_message_text(msg)")
    lines.append("        return")
    lines.append("    ruled = logic.apply_rules({\"choice\": data, \"text\": data, **dict(context.user_data.get(\"collected\") or {})})")
    lines.append("    context.user_data[\"collected\"] = ruled")
    lines.append("    if ruled.get(\"_messages\"):")
    lines.append("        await query.edit_message_text(\" | \".join(str(m) for m in ruled[\"_messages\"][:5]))")
    lines.append("        return")
    if inf.decisions:
        dname = _ident(inf.decisions[0].name)
        lines.append(f"    branch = logic.{dname}(data)")
        lines.append("    context.user_data[\"branch\"] = branch")
        if step_ids:
            lines.append(f"    _prompts = {_py(step_labels)}")
            lines.append("    msg = _prompts.get(branch) or str(branch)")
            lines.append("    await query.edit_message_text(msg)")
        else:
            lines.append("    await query.edit_message_text(str(branch))")
    else:
        lines.append("    await query.edit_message_text(data or \"تم\")")
    lines.append("")
    return "\n".join(lines) + "\n"


def _emit_container(inf: InferenceResult) -> str:
    lines = [
        '"""DI container — stores from inferred schemas only."""',
        "from __future__ import annotations",
        "from functools import lru_cache",
        "from app import store as store_mod",
        "",
        "",
        "class Container:",
        "    def __init__(self) -> None:",
    ]
    if inf.schemas:
        first = True
        for sch in inf.schemas:
            sname = _ident(sch.table)
            cstore = _cls(sch.table) + "Store"
            lines.append(f"        self.{sname} = store_mod.{cstore}()")
            if first:
                lines.append(f"        self.primary_store = self.{sname}")
                first = False
    else:
        lines.append("        self.primary_store = store_mod.RecordStore()")
    lines += [
        "",
        "",
        "@lru_cache(maxsize=1)",
        "def get_container() -> Container:",
        "    return Container()",
        "",
    ]
    return "\n".join(lines) + "\n"


def _emit_config(inf: InferenceResult) -> str:
    lines = [
        '"""Typed config from env."""',
        "from __future__ import annotations",
        "from functools import lru_cache",
        "from pydantic import Field",
        "from pydantic_settings import BaseSettings, SettingsConfigDict",
        "",
        "",
        "class Settings(BaseSettings):",
        "    model_config = SettingsConfigDict(env_file=\".env\", env_file_encoding=\"utf-8\", extra=\"ignore\")",
        "    telegram_bot_token: str = Field(..., min_length=20)",
        "    admin_user_ids: str = \"\"",
        "    log_level: str = \"INFO\"",
    ]
    if inf.wants_database:
        lines.append("    database_url: str = \"sqlite+aiosqlite:///./bot.db\"")
    lines += [
        "",
        "",
        "@lru_cache(maxsize=1)",
        "def get_settings() -> Settings:",
        "    return Settings()",
        "",
    ]
    return "\n".join(lines)


def _emit_main(inf: InferenceResult) -> str:
    commands = list(inf.commands or [])
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
    if inf.wants_files:
        regs.append("    app.add_handler(MessageHandler(filters.PHOTO, message_handler))")
        regs.append("    app.add_handler(MessageHandler(filters.Document.ALL, message_handler))")

    bot_cmds = []
    for c in commands:
        bot_cmds.append(f"        BotCommand({_py(c.name)}, {_py((c.description or c.name)[:50])}),")
    bot_block = "\n".join(bot_cmds) if bot_cmds else '        BotCommand("start", "start"),'

    return (
        '"""Entry — wiring inferred handlers only."""\n'
        "from __future__ import annotations\n"
        "import logging\n"
        "import sys\n"
        "from telegram import BotCommand, Update\n"
        "from telegram.ext import Application, CallbackQueryHandler, CommandHandler, MessageHandler, filters\n"
        "from app.config import get_settings\n"
        + "\n".join(imports) + "\n\n"
        "logging.basicConfig(\n"
        "    format=\"%(asctime)s | %(levelname)-8s | %(name)s | %(message)s\",\n"
        "    level=logging.INFO,\n"
        "    stream=sys.stdout,\n"
        ")\n"
        "logger = logging.getLogger(\"bot\")\n\n\n"
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
        "    logger.info(\"starting\")\n"
        "    build_application().run_polling(allowed_updates=Update.ALL_TYPES)\n\n\n"
        "if __name__ == \"__main__\":\n"
        "    main()\n"
    )


def _emit_requirements(inf: InferenceResult) -> str:
    reqs = [
        "python-telegram-bot>=21.0",
        "pydantic>=2.0",
        "pydantic-settings>=2.0",
    ]
    if inf.wants_database:
        reqs += ["sqlalchemy[asyncio]>=2.0", "aiosqlite>=0.19"]
    return "\n".join(reqs) + "\n"


def _emit_env(inf: InferenceResult) -> str:
    lines = ["TELEGRAM_BOT_TOKEN=", "ADMIN_USER_IDS=", "LOG_LEVEL=INFO"]
    if inf.wants_database:
        lines.append("DATABASE_URL=sqlite+aiosqlite:///./bot.db")
    return "\n".join(lines) + "\n"


def transpile(inf: InferenceResult, out_dir: str | Path) -> list[str]:
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
    w("app/models.py", _emit_schema_module(inf))
    w("app/store.py", _emit_store_module(inf))
    w("app/logic.py", _emit_logic_module(inf))
    w("app/handlers.py", _emit_handlers_module(inf))
    w("app/container.py", _emit_container(inf))
    w("app/config.py", _emit_config(inf))
    w("main.py", _emit_main(inf))
    w("requirements.txt", _emit_requirements(inf))
    w(".env.example", _emit_env(inf))
    return written
