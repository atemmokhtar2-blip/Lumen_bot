"""
Micro-Transpiler — Statement by Statement from InferenceResult only.
No domain templates. No canned shop/ticket/admin packs.
Emits Python syntax that expresses inferred relations, operations, UI surface.
"""

from __future__ import annotations

from ..ontology.telegram_capabilities import (
    any_needs_user_target,
    capability_by_id,
)

import re
from pathlib import Path
from typing import Any

from ..inference.engine import InferenceResult
from .tools_emit import emit_tools_module


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


def _surface_norm(value: str) -> str:
    """Normalize Arabic/English UI labels for deterministic button routing."""
    s = (value or "").strip().lower()
    for a, b in (("أ", "ا"), ("إ", "ا"), ("آ", "ا"), ("ة", "ه"), ("ى", "ي")):
        s = s.replace(a, b)
    return re.sub(r"[^a-z0-9\u0600-\u06ff]+", " ", s).strip()


def _surface_aliases(value: str) -> set[str]:
    s = _surface_norm(value)
    aliases = {s, s.replace("ال", "", 1) if s.startswith("ال") else s}
    groups = {
        "product": {"product", "products", "منتج", "منتجات", "صنف", "اصناف"},
        "cart": {"cart", "basket", "سله", "سلة", "سلة الشراء", "عربه", "عربة"},
        "checkout": {"checkout", "شراء", "دفع", "اتمام الطلب", "طلب الاوردر"},
        "ticket": {"ticket", "tickets", "تذكره", "تذاكر", "تذاكر الدعم"},
        "support": {"support", "دعم", "خدمة العملاء", "خدمة عملاء"},
        "warn": {"warn", "warning", "تحذير", "انذار"},
        "ban": {"ban", "حظر"},
        "mute": {"mute", "كتم"},
    }
    for canonical, words in groups.items():
        normalized = {_surface_norm(w) for w in words}
        if s in normalized or any(a in normalized for a in aliases):
            aliases.update(normalized)
            aliases.add(canonical)
    return {a for a in aliases if a}


def _surface_matches(label: str, command_name: str, description: str) -> bool:
    left = _surface_aliases(label)
    right = _surface_aliases(command_name) | _surface_aliases(description)
    if left & right:
        return True
    # Match meaningful words, while avoiding one-letter/common Arabic tokens.
    lwords = {w for x in left for w in x.split() if len(w) >= 3}
    rwords = {w for x in right for w in x.split() if len(w) >= 3}
    return bool(lwords & rwords)


# ── schema ──────────────────────────────────────────────────────────────






def _cmd_capability_map(commands) -> dict[str, list[str]]:
    """command name -> capability ids (only evidenced ones)."""
    out: dict[str, list[str]] = {}
    for cmd in commands or []:
        caps = [c for c in list(getattr(cmd, "capabilities", None) or []) if capability_by_id(c)]
        if caps:
            out[cmd.name] = caps
    return out



def _harden_handlers_source(src: str) -> str:
    """Wrap every command handler so exceptions never leave the user with silence."""
    if "async def _safe_reply" not in src:
        needle = "from app.container import get_container\n"
        inject = (
            needle
            + "\n"
            + "async def _safe_reply(message, text: str) -> None:\n"
            + "    if message is None:\n"
            + "        return\n"
            + "    try:\n"
            + "        await message.reply_text(str(text)[:3500])\n"
            + "    except Exception:\n"
            + "        pass\n"
            + "\n"
        )
        if needle in src:
            src = src.replace(needle, inject, 1)
    header_re = re.compile(
        r"(async def \w+_handler\(update: Update, context: ContextTypes\.DEFAULT_TYPE\) -> None:\n)"
    )
    parts = header_re.split(src)
    if len(parts) < 3:
        return src
    out = [parts[0]]
    i = 1
    while i < len(parts):
        header = parts[i]
        body = parts[i + 1] if i + 1 < len(parts) else ""
        # Don't double-wrap
        if body.lstrip().startswith("try:"):
            out.append(header)
            out.append(body)
            i += 2
            continue
        # Indent body one level and wrap
        indented_lines = []
        for ln in body.splitlines(keepends=True):
            if ln.strip() == "":
                indented_lines.append(ln)
            else:
                indented_lines.append("    " + ln)
        wrapped = (
            "    try:\n"
            + "".join(indented_lines).rstrip()
            + "\n"
            + "    except Exception as _exc:\n"
            + "        try:\n"
            + "            await _safe_reply(message, f\"خطأ أثناء تنفيذ الأمر: {_exc}\")\n"
            + "        except Exception:\n"
            + "            pass\n\n"
        )
        out.append(header)
        out.append(wrapped)
        i += 2
    return "".join(out)


def _emit_capability_runtime(lines: list[str], commands, *, need_permissions: bool) -> None:
    """
    Emit shared structural runtime for Telegram capabilities.
    Deep conversion: one dispatcher, rich target resolution, chat guards.
    Not a domain template — only emits what inferred capabilities require.
    """
    cap_map = _cmd_capability_map(commands)
    # Always emit map so callbacks can reference it safely
    lines.append("CAPABILITY_BY_CMD: dict[str, list[str]] = {")
    for name, caps in cap_map.items():
        lines.append(f"    {_py(name)}: [{', '.join(_py(c) for c in caps)}],")
    lines.append("}")
    lines.append("")
    lines.append("")
    if not cap_map:
        return

    # Deep target resolution
    lines.append("async def _resolve_target_user(update, args):")
    lines.append('    """Deep target resolution: reply, entities, numeric id, @username."""')
    lines.append("    message = update.effective_message")
    lines.append("    # 1) reply-to")
    lines.append("    if message is not None and message.reply_to_message and message.reply_to_message.from_user:")
    lines.append("        u = message.reply_to_message.from_user")
    lines.append("        return int(u.id), (u.username or u.full_name or str(u.id))")
    lines.append("    # 2) text_mention / mention entities")
    lines.append("    if message is not None and message.entities:")
    lines.append("        for ent in message.entities:")
    lines.append("            if ent.type == 'text_mention' and ent.user is not None:")
    lines.append("                u = ent.user")
    lines.append("                return int(u.id), (u.username or u.full_name or str(u.id))")
    lines.append("            if ent.type == 'mention' and message.text:")
    lines.append("                uname = message.text[ent.offset: ent.offset + ent.length]")
    lines.append("                return uname, uname")
    lines.append("    # 3) explicit args")
    lines.append("    if args:")
    lines.append("        raw = str(args[0]).strip()")
    lines.append("        if raw.isdigit():")
    lines.append("            return int(raw), raw")
    lines.append("        if raw.startswith('id:') and raw[3:].strip().isdigit():")
    lines.append("            return int(raw[3:].strip()), raw[3:].strip()")
    lines.append("        if raw.startswith('@') and len(raw) > 1:")
    lines.append("            return raw, raw")
    lines.append("        if re.fullmatch(r'[A-Za-z][A-Za-z0-9_]{4,31}', raw):")
    lines.append("            return f'@{raw}', f'@{raw}'")
    lines.append("    return None, None")
    lines.append("")
    lines.append("")

    lines.append("def _parse_optional_duration(args) -> int | None:")
    lines.append('    """Second numeric arg as duration seconds (structural, optional)."""')
    lines.append("    if not args or len(args) < 2:")
    lines.append("        return None")
    lines.append("    raw = str(args[1]).strip().lower()")
    lines.append("    if raw.isdigit():")
    lines.append("        return max(0, int(raw))")
    lines.append("    m = re.fullmatch(r'(\\d+)([smhd])', raw)")
    lines.append("    if not m:")
    lines.append("        return None")
    lines.append("    n, unit = int(m.group(1)), m.group(2)")
    lines.append("    mult = {'s': 1, 'm': 60, 'h': 3600, 'd': 86400}[unit]")
    lines.append("    return max(0, n * mult)")
    lines.append("")
    lines.append("")

    lines.append("async def _run_capabilities(update, context, cap_ids: list[str], args: list) -> None:")
    lines.append('    """Execute evidenced Telegram API capabilities with deep guards."""')
    lines.append("    message = update.effective_message")
    lines.append("    chat = update.effective_chat")
    lines.append("    user = update.effective_user")
    lines.append("    if message is None or chat is None:")
    lines.append("        return")
    lines.append("    chat_id = chat.id")
    lines.append("    # Admin-style capabilities require a group/supergroup context")
    lines.append("    needs_group = any(c in (")
    lines.append("        'ban_chat_member', 'kick_chat_member', 'unban_chat_member',")
    lines.append("        'restrict_chat_member', 'unrestrict_chat_member', 'promote_chat_member',")
    lines.append("    ) for c in cap_ids)")
    lines.append("    if needs_group and getattr(chat, 'type', '') not in ('group', 'supergroup'):")
    lines.append("        await message.reply_text('هذا الأمر يعمل داخل المجموعات فقط')")
    lines.append("        return")
    lines.append("")
    lines.append("    needs_target = any(c in (")
    lines.append("        'ban_chat_member', 'kick_chat_member', 'unban_chat_member',")
    lines.append("        'restrict_chat_member', 'unrestrict_chat_member', 'promote_chat_member',")
    lines.append("    ) for c in cap_ids)")
    lines.append("    target_id = target_label = None")
    lines.append("    if needs_target:")
    lines.append("        target_id, target_label = await _resolve_target_user(update, args)")
    lines.append("        if target_id is None:")
    lines.append("            await message.reply_text('حدد العضو: رد على رسالته، أو منشن، أو أرسل المعرّف بعد الأمر')")
    lines.append("            return")
    lines.append("        # Protect against acting on self/bot when numeric")
    lines.append("        if isinstance(target_id, int):")
    lines.append("            if user and target_id == user.id:")
    lines.append("                await message.reply_text('لا يمكن تنفيذ الأمر على نفسك')")
    lines.append("                return")
    lines.append("            try:")
    lines.append("                me = await context.bot.get_me()")
    lines.append("                if me and target_id == me.id:")
    lines.append("                    await message.reply_text('لا يمكن تنفيذ الأمر على البوت')")
    lines.append("                    return")
    lines.append("            except Exception:")
    lines.append("                pass")
    lines.append("")
    lines.append("    duration = _parse_optional_duration(args)")
    lines.append("    until_date = None")
    lines.append("    if duration:")
    lines.append("        until_date = int(time.time()) + int(duration)")
    lines.append("")
    lines.append("    async def _as_user_id(tid):")
    lines.append("        if isinstance(tid, int):")
    lines.append("            return tid")
    lines.append("        # username string — resolve via get_chat when possible")
    lines.append("        try:")
    lines.append("            ch = await context.bot.get_chat(tid)")
    lines.append("            return int(ch.id)")
    lines.append("        except Exception:")
    lines.append("            return tid")
    lines.append("")
    lines.append("    try:")
    lines.append("        for cid in cap_ids:")
    lines.append("            if cid == 'ban_chat_member':")
    lines.append("                uid = await _as_user_id(target_id)")
    lines.append("                kwargs = {'chat_id': chat_id, 'user_id': int(uid)}")
    lines.append("                if until_date:")
    lines.append("                    kwargs['until_date'] = until_date")
    lines.append("                await context.bot.ban_chat_member(**kwargs)")
    lines.append("                await message.reply_text(f'تم الحظر: {target_label}')")
    lines.append("            elif cid == 'kick_chat_member':")
    lines.append("                uid = await _as_user_id(target_id)")
    lines.append("                await context.bot.ban_chat_member(chat_id=chat_id, user_id=int(uid))")
    lines.append("                await context.bot.unban_chat_member(chat_id=chat_id, user_id=int(uid))")
    lines.append("                await message.reply_text(f'تم الطرد: {target_label}')")
    lines.append("            elif cid == 'unban_chat_member':")
    lines.append("                uid = await _as_user_id(target_id)")
    lines.append("                await context.bot.unban_chat_member(chat_id=chat_id, user_id=int(uid))")
    lines.append("                await message.reply_text(f'تم فك الحظر: {target_label}')")
    lines.append("            elif cid == 'restrict_chat_member':")
    lines.append("                uid = await _as_user_id(target_id)")
    lines.append("                perms = ChatPermissions(can_send_messages=False)")
    lines.append("                kwargs = {'chat_id': chat_id, 'user_id': int(uid), 'permissions': perms}")
    lines.append("                if until_date:")
    lines.append("                    kwargs['until_date'] = until_date")
    lines.append("                await context.bot.restrict_chat_member(**kwargs)")
    lines.append("                extra = f' لمدة {duration}ث' if duration else ''")
    lines.append("                await message.reply_text(f'تم الكتم: {target_label}{extra}')")
    lines.append("            elif cid == 'unrestrict_chat_member':")
    lines.append("                uid = await _as_user_id(target_id)")
    lines.append("                perms = ChatPermissions(")
    lines.append("                    can_send_messages=True,")
    lines.append("                    can_send_media_messages=True,")
    lines.append("                    can_send_other_messages=True,")
    lines.append("                    can_add_web_page_previews=True,")
    lines.append("                )")
    lines.append("                await context.bot.restrict_chat_member(")
    lines.append("                    chat_id=chat_id, user_id=int(uid), permissions=perms)")
    lines.append("                await message.reply_text(f'تم فك الكتم: {target_label}')")
    lines.append("            elif cid == 'promote_chat_member':")
    lines.append("                uid = await _as_user_id(target_id)")
    lines.append("                await context.bot.promote_chat_member(")
    lines.append("                    chat_id=chat_id, user_id=int(uid),")
    lines.append("                    can_manage_chat=True, can_delete_messages=True,")
    lines.append("                    can_restrict_members=True, can_invite_users=True,")
    lines.append("                )")
    lines.append("                await message.reply_text(f'تمت الترقية: {target_label}')")
    lines.append("            elif cid == 'delete_message':")
    lines.append("                if message.reply_to_message:")
    lines.append("                    await context.bot.delete_message(")
    lines.append("                        chat_id=chat_id,")
    lines.append("                        message_id=message.reply_to_message.message_id,")
    lines.append("                    )")
    lines.append("                    await message.reply_text('تم حذف الرسالة')")
    lines.append("                else:")
    lines.append("                    await message.reply_text('رد على الرسالة لحذفها')")
    lines.append("            elif cid == 'pin_chat_message':")
    lines.append("                if message.reply_to_message:")
    lines.append("                    await context.bot.pin_chat_message(")
    lines.append("                        chat_id=chat_id,")
    lines.append("                        message_id=message.reply_to_message.message_id,")
    lines.append("                    )")
    lines.append("                    await message.reply_text('تم تثبيت الرسالة')")
    lines.append("                else:")
    lines.append("                    await message.reply_text('رد على الرسالة لتثبيتها')")
    lines.append("            elif cid == 'unpin_chat_message':")
    lines.append("                mid = message.reply_to_message.message_id if message.reply_to_message else None")
    lines.append("                await context.bot.unpin_chat_message(chat_id=chat_id, message_id=mid)")
    lines.append("                await message.reply_text('تم إلغاء التثبيت')")
    lines.append("            else:")
    lines.append("                await message.reply_text(f'capability:{cid}')")
    lines.append("    except Exception as exc:")
    lines.append("        err = str(exc).lower()")
    lines.append("        if 'not enough rights' in err or 'chat_admin' in err or 'not an admin' in err:")
    lines.append("            await message.reply_text('البوت يحتاج صلاحيات مشرف كافية')")
    lines.append("        elif 'user_not_found' in err or 'user not found' in err:")
    lines.append("            await message.reply_text('المستخدم غير موجود في هذه المحادثة')")
    lines.append("        elif 'can\\'t parse' in err or 'invalid' in err and 'user' in err:")
    lines.append("            await message.reply_text('تعذر التعرف على العضو — استخدم ردًا أو معرّفًا رقميًا')")
    lines.append("        else:")
    lines.append("            await message.reply_text(f'فشل التنفيذ: {exc}')")
    lines.append("")
    lines.append("")


def _emit_capability_body(lines: list[str], cmd, *, _py) -> bool:
    """
    Thin per-handler bridge into shared _run_capabilities.
    Returns True when command has evidenced Telegram capabilities.
    """
    caps = [c for c in list(getattr(cmd, "capabilities", None) or []) if capability_by_id(c)]
    if not caps:
        return False
    lines.append(f"    await _run_capabilities(update, context, CAPABILITY_BY_CMD.get({_py(cmd.name)}, []), args)")
    return True



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




def _emit_services_module(inf: InferenceResult) -> str:
    """Generic entity services from inferred schemas/entities only — no domain packs."""
    lines = [
        '"""Services derived from entities in this request only."""',
        "from __future__ import annotations",
        "from typing import Any",
        "from app.container import get_container",
        "",
        "async def create_record(entity: str, user_id: int, data: dict[str, Any]) -> str:",
        "    store = get_container().store_for(entity)",
        "    if store is None:",
        "        # memory fallback",
        "        return 'mem:' + entity",
        "    payload = dict(data)",
        "    payload['user_id'] = user_id",
        "    if hasattr(store, 'create'):",
        "        return str(await store.create(**{k: v for k, v in payload.items() if not str(k).startswith('_')}))",
        "    return 'ok'",
        "",
        "async def list_records(entity: str, user_id: int) -> list[dict[str, Any]]:",
        "    store = get_container().store_for(entity)",
        "    if store is None:",
        "        return []",
        "    if hasattr(store, 'list_by_user'):",
        "        try:",
        "            return list(await store.list_by_user(user_id))[:50]",
        "        except Exception:",
        "            pass",
        "    if hasattr(store, 'list_all'):",
        "        try:",
        "            rows = await store.list_all()",
        "            return [r for r in rows if not isinstance(r, dict) or int(r.get('user_id') or 0) == user_id][:50]",
        "        except Exception:",
        "            return []",
        "    return []",
        "",
        "async def update_record(entity: str, record_id: str, **fields: Any) -> bool:",
        "    store = get_container().store_for(entity)",
        "    if store is None or not hasattr(store, 'update_status'):",
        "        return False",
        "    try:",
        "        if 'status' in fields:",
        "            return bool(await store.update_status(str(record_id), str(fields['status'])))",
        "    except Exception:",
        "        return False",
        "    return False",
        "",
    ]
    return "\n".join(lines) + "\n"

def _emit_handlers_module(inf: InferenceResult) -> str:
    """Handlers from inferred commands, buttons, steps — no domain packs."""
    commands = list(inf.commands or [])
    _JUNK_CMD = {'ssl','tls','example','information','com','http','https','www','order','pin','records','status','certificate','headers'}
    commands = [c for c in commands if getattr(c,'name','') not in _JUNK_CMD]
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
        if c in ("stats", "statistics", "dashboard") or c.endswith("_stats"):
            return "stats"
        if c.startswith("my_") or c in ("progress", "score", "history"):
            return "mine"
        if c in ("courses", "catalog") or any(x in c for x in ("list", "products", "items", "tickets", "orders")):
            return "list"
        if any(x in c for x in ("ban", "delete", "remove", "cancel", "drop")):
            return "mutate"
        if any(x in c for x in ("broadcast", "notify")):
            return "broadcast"
        if c in (
            "points", "rank", "daily", "wallet", "balance", "deposit", "withdraw",
            "referral", "invite", "profile", "settings", "menu", "tasks", "missions",
            "gift", "top", "leaderboard", "id", "info", "ping", "about", "support",
            "contact", "language", "news", "events", "notifications", "feedback",
            "report", "suggest", "search", "admin", "panel",
        ):
            return "account"
        return "generic"

    all_caps: list[str] = []
    for _c in commands:
        all_caps.extend(list(getattr(_c, "capabilities", None) or []))
    need_target_helper = any_needs_user_target(all_caps)
    need_permissions = any(
        c in ("restrict_chat_member", "unrestrict_chat_member") for c in all_caps
    )
    tg_imports = "Update, InlineKeyboardButton, InlineKeyboardMarkup"
    if need_permissions:
        tg_imports += ", ChatPermissions"

    lines: list[str] = [
        '"""Handlers from inferred commands/buttons/steps only."""',
        "from __future__ import annotations",
        "import re",
        "import time",
        f"from telegram import {tg_imports}",
        "from telegram.ext import ContextTypes",
        "from app import logic",
        "from app.container import get_container",
        "",
        "",
    ]
    _wiz = list(getattr(inf, "wizards", None) or [])
    _dyn = [str(t.get("id") or "") for t in (getattr(inf, "dynamic_tools", None) or []) if isinstance(t, dict)]
    _tool_ids = sorted({x for x in (_dyn + [c.name for c in commands if c.name not in ("start", "help")]) if x})
    lines.append("TOOL_IDS: list[str] = " + repr(_tool_ids))
    lines.append("FLOWS: dict[str, list[dict[str, str]]] = {")
    for w in _wiz:
        steps = [st for st in (w.get("steps") or []) if isinstance(st, dict) and st.get("key")]
        if not steps:
            continue
        wid = str(w.get("id") or w.get("command") or "flow")
        lines.append(f"    {_py(wid)}: [")
        for st in steps:
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
    cmd_name_set = {c.name for c in commands}
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
            # Prefer exact label==description; avoid weak substring (مهمة matching إضافة مهمة)
            if desc and desc == label:
                btn_to_cmd[cb] = c.name
                break
            if desc and label and (label.endswith(desc) or desc.endswith(label)) and abs(len(desc)-len(label)) <= 4:
                btn_to_cmd[cb] = c.name
                break
            # stem names in label — never use fuzzy surface for these stems
            # Generic stem overlap: command name tokens vs label (no domain list)
            name_toks = [x for x in c.name.replace("_", " ").split() if len(x) > 2]
            lab_l = label.lower()
            if name_toks and all(tok.lower() in lab_l or tok in label for tok in name_toks[:2]):
                btn_to_cmd[cb] = c.name
                break
            # Linguistic Arabic action words vs command-name shape (no fixed domain pack).
            _ar_action = {
                "new": ("إضافة", "اضافه", "اضف", "جديد", "مهمة جديدة"),
                "add": ("إضافة", "اضافه", "اضف", "جديد"),
                "create": ("إنشاء", "انشاء", "اضافه"),
                "my": ("مهامي", "قائمتي", "عملائي", "طلباتي"),
                "list": ("قائمة", "قائمه", "عرض"),
                "all": ("كل", "جميع"),
                "complete": ("إنهاء", "انهاء", "اكمال", "إكمال", "تم"),
                "done": ("إنهاء", "تم", "اكتمل"),
                "delete": ("حذف", "ازالة", "إزالة"),
                "remove": ("حذف", "ازالة"),
            }
            cn_parts = set(c.name.lower().replace("-", "_").split("_"))
            matched = False
            for key, words in _ar_action.items():
                if key in cn_parts and any(w in label for w in words):
                    btn_to_cmd[cb] = c.name
                    matched = True
                    break
            if matched:
                break
            if _surface_matches(label, c.name, desc):
                btn_to_cmd[cb] = c.name
                break

    lines.append("BUTTON_TO_CMD: dict[str, str] = {")
    for cb, cn in btn_to_cmd.items():
        lines.append(f"    {_py(cb)}: {_py(cn)},")
    lines.append("}")
    lines.append("")
    lines.append("CALLBACK_LABELS: dict[str, str] = {")
    for label, cb in kb_items:
        lines.append(f"    {_py(cb)}: {_py(label)},")
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


    # Shared deep capability runtime (only if any command evidenced Telegram API caps)
    _emit_capability_runtime(lines, commands, need_permissions=need_permissions)

    # start — welcome + short command map
    # start — welcome + FULL command map (never silently truncate)
    start_bits = ["مرحباً بك 👋", ""]
    admin_names = {c.name for c in commands if getattr(c, "admin_only", False)}
    user_cmds = [c for c in commands if c.name not in admin_names]
    admin_cmds = [c for c in commands if c.name in admin_names]
    if user_cmds:
        start_bits.append("أوامر المستخدم:")
        for c in user_cmds:
            start_bits.append(f"/{c.name} — {c.description or c.name}")
    if admin_cmds:
        start_bits.append("")
        start_bits.append("أوامر الإدارة:")
        for c in admin_cmds:
            start_bits.append(f"/{c.name} — {c.description or c.name}")
    start_msg = "\n".join(start_bits)
    # Telegram hard limit ~4096; keep a safe head for the first message
    if len(start_msg) > 3500:
        start_msg = "\n".join(start_bits[:80]) + "\n…\nاستخدم /help لعرض باقي الأوامر."
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
    # Emit chunked help for large command surfaces
    lines.append(f"    _help = {_py(help_text)}")
    lines.append("    if len(_help) <= 3500:")
    lines.append("        await message.reply_text(_help)")
    lines.append("    else:")
    lines.append("        chunk: list[str] = []")
    lines.append("        size = 0")
    lines.append("        for line in _help.splitlines():")
    lines.append("            if size + len(line) + 1 > 3400 and chunk:")
    lines.append("                await message.reply_text(chr(10).join(chunk))")
    lines.append("                chunk, size = [], 0")
    lines.append("            chunk.append(line)")
    lines.append("            size += len(line) + 1")
    lines.append("        if chunk:")
    lines.append("            await message.reply_text(chr(10).join(chunk))")
    lines.append("")
    lines.append("")



    # one handler per inferred command — structural only (no domain packs)
    for cmd in commands:
        if cmd.name in ("start", "help"):
            continue
        fn = _ident(cmd.name) + "_handler"
        caps = list(getattr(cmd, "capabilities", None) or [])
        cn = cmd.name.lower()
        lines.append(f"async def {fn}(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:")
        lines.append("    message = update.effective_message")
        lines.append("    if message is None:")
        lines.append("        return")
        lines.append("    user = update.effective_user")
        lines.append("    uid = int(user.id) if user else 0")
        lines.append("    args: list[str] = []")
        lines.append("    if message.text and ' ' in message.text:")
        lines.append("        args = message.text.split()[1:]")
        lines.append("    try:")
        lines.append(f"        _admin_only = {str(bool(cmd.admin_only))}")
        lines.append("        if _admin_only:")
        lines.append("            from app.config import get_settings as _gs")
        lines.append("            _settings = _gs()")
        lines.append("            _admins: set[int] = set()")
        lines.append("            for _part in str(getattr(_settings, 'admin_user_ids', '') or '').split(','):")
        lines.append("                _part = _part.strip()")
        lines.append("                if _part.isdigit():")
        lines.append("                    _admins.add(int(_part))")
        lines.append("            if _admins and uid not in _admins:")
        lines.append("                await message.reply_text('هذا الأمر للمشرفين فقط.')")
        lines.append("                return")
        # Only enforce admin when command marked admin_only
        # Wizard/flow
        lines.append("        target = ' '.join(args).strip()")
        lines.append("        from app.tools import TOOL_IDS, run_tool")
        lines.append(f"        _has_tool = {_py(cn)} in TOOL_IDS")
        lines.append(f"        _has_flow = {_py(cmd.name)} in FLOWS and bool(FLOWS.get({_py(cmd.name)}))")
        # args present + tool → execute tool immediately
        lines.append("        if _has_tool and target:")
        lines.append(f"            await message.reply_text(run_tool({_py(cn)}, target)[:3500])")
        lines.append("            return")
        # no args: prefer multi-step flow if defined, else prompt for tool input
        lines.append("        if _has_flow and not target:")
        lines.append(f"            await _start_flow(message, context, {_py(cmd.name)})")
        lines.append("            return")
        lines.append("        if _has_tool and not target:")
        lines.append(f"            context.user_data['await_tool'] = {_py(cn)}")
        lines.append("            await message.reply_text('أرسل القيمة المطلوبة:')")
        lines.append("            return")
        # Telegram capabilities
        if caps:
            lines.append(f"        _caps = CAPABILITY_BY_CMD.get({_py(cmd.name)}, [])")
            lines.append("        if _caps:")
            lines.append("            await _run_capabilities(update, context, _caps, args)")
            lines.append("            return")
        # Structural stems from command name only (no domain packs)
        lines.append(f"        _cn = {_py(cn)}")
        lines.append("        app_data = context.application.bot_data")
        lines.append("        bucket = app_data.setdefault('records', {})")
        lines.append("        mine = bucket.setdefault(str(uid), [])")
        # Structural stems from command-name shape only (no domain rename packs).
        lines.append("        _is_listish = (")
        lines.append("            _cn.startswith('list_') or _cn.startswith('my_') or")
        lines.append("            _cn in ('mine', 'list', 'catalog', 'cart', 'orders', 'products', 'basket') or")
        lines.append("            str(FLOW_KIND.get(_cn) or '') in ('list', 'mine')")
        lines.append("        )")
        lines.append("        if _is_listish:")
        lines.append("            try:")
        lines.append("                from app.services import list_records")
        lines.append("                ent = str(FLOW_ENTITY.get(_cn) or '')")
        lines.append("                if not ent:")
        lines.append("                    if _cn.startswith('list_'):")
        lines.append("                        ent = _cn[5:]")
        lines.append("                    elif _cn.startswith('my_'):")
        lines.append("                        ent = _cn[3:]")
        lines.append("                    elif _cn.startswith('all_'):")
        lines.append("                        ent = _cn[4:]")
        lines.append("                    else:")
        lines.append("                        ent = 'record'")
        lines.append("                if ent and ent.endswith('s') and len(ent) > 3 and ent[:1].islower():")
        lines.append("                    ent = ent[:-1]")
        lines.append("                rows = await list_records(ent, uid)")
        lines.append("            except Exception:")
        lines.append("                rows = []")
        lines.append("            if not rows:")
        lines.append("                rows = [r for r in mine if (r.get('status') or 'open') != 'done']")
        lines.append("            if not rows:")
        lines.append(f"                await message.reply_text({_py((cmd.description or 'لا توجد سجلات'))})")
        lines.append("            else:")
        lines.append("                lines_out = []")
        lines.append("                for i, r in enumerate(rows[:30], 1):")
        lines.append("                    if isinstance(r, dict):")
        lines.append("                        lines_out.append(str(i) + '. ' + ' | '.join(f'{k}={v}' for k,v in list(r.items())[:6]))")
        lines.append("                    else:")
        lines.append("                        lines_out.append(str(i) + '. ' + str(r))")
        lines.append("                await message.reply_text(chr(10).join(lines_out)[:3500])")
        lines.append("            return")
        lines.append("        if _cn in ('mine', 'list') or _cn.startswith('my_') or _cn.startswith('list_'):")
        lines.append("            active = [r for r in mine if (r.get('status') or 'open') != 'done']")
        lines.append("            if not active:")
        lines.append(f"                await message.reply_text({_py((cmd.description or 'لا عناصر') )})")
        lines.append("            else:")
        lines.append("                lines_out = [f'{i}. {r.get(\"title\") or r}' for i,r in enumerate(active[:30],1)]")
        lines.append("                rows = []")
        lines.append("                for i,_r in enumerate(active[:30]):")
        lines.append("                    rows.append([")
        lines.append("                        InlineKeyboardButton('OK', callback_data=f'done:{i}'),")
        lines.append("                        InlineKeyboardButton('X', callback_data=f'del:{i}'),")
        lines.append("                    ])")
        lines.append("                await message.reply_text(chr(10).join(lines_out), reply_markup=InlineKeyboardMarkup(rows))")
        lines.append("        elif (_cn.startswith('new_') or _cn.startswith('add_') or _cn.startswith('create_')")
        lines.append("                or _cn in ('add', 'create', 'new')):")
        lines.append("            context.user_data['flow'] = _cn")
        lines.append("            context.user_data['step'] = 0")
        lines.append("            context.user_data['data'] = {}")
        lines.append("            if FLOWS.get(_cn):")
        lines.append("                await _start_flow(message, context, _cn)")
        lines.append("            else:")
        lines.append("                await message.reply_text('أرسل النص للحفظ:')")
        lines.append("                context.user_data['flow'] = 'collect_title'")
        lines.append("                context.user_data['step'] = 0")
        lines.append("                context.user_data['data'] = {}")
        lines.append("                FLOWS.setdefault('collect_title', [{'key': 'title', 'prompt': 'أرسل النص للحفظ:'}])")
        lines.append("        elif (_cn in ('complete', 'done')")
        lines.append("                or _cn.startswith('complete_') or _cn.startswith('done_')):")
        lines.append("            await message.reply_text('اختر عنصراً من القائمة أو أرسل رقمه.')")
        lines.append("        elif (_cn in ('remove', 'delete')")
        lines.append("                or _cn.startswith('delete_') or _cn.startswith('remove_')):")
        lines.append("            await message.reply_text('اختر عنصراً من القائمة للحذف.')")
        lines.append("        elif _cn == 'menu' or _cn.startswith('show_'):")
        lines.append("            kb = main_keyboard()")
        lines.append("            await message.reply_text('القائمة:', reply_markup=kb)")
        lines.append("        elif _cn == 'ping':")
        lines.append("            await message.reply_text('pong')")
        lines.append("        elif _cn == 'id':")
        lines.append("            await message.reply_text('User ID: ' + str(uid) + ' | Chat: ' + str(message.chat_id))")
        lines.append("        if False:  # defensive pack removed")
        lines.append("            target = ' '.join(args).strip()")
        lines.append("            if not target:")
        lines.append(f"                if {_py(cmd.name)} in FLOWS and FLOWS.get({_py(cmd.name)}):")
        lines.append(f"                    await _start_flow(message, context, {_py(cmd.name)})")
        lines.append("                    return")
        lines.append("                await message.reply_text('أرسل الهدف بعد الأمر، مثال: /domain_scan example.com')")
        lines.append("                return")
        lines.append("            try:")
        lines.append("                from app.tools import run_evidenced_checks")
        lines.append("                await message.reply_text(run_evidenced_checks(target)[:3500])")
        lines.append("            except Exception as _te:")
        lines.append("                await message.reply_text('خطأ فحص: ' + str(_te))")
        lines.append("            return")
        lines.append("        else:")
        lines.append(f"            await message.reply_text({_py('✅ /' + cmd.name + ' — ' + (cmd.description or cmd.name))})")
        lines.append("    except Exception as _exc:")
        lines.append("        try:")
        lines.append("            await message.reply_text('خطأ: ' + str(_exc))")
        lines.append("        except Exception:")
        lines.append("            pass")
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
    lines.append("    _await = ud.get('await_tool')")
    lines.append("    if _await and text and not text.startswith('/'):")
    lines.append("        from app.tools import run_tool")
    lines.append("        ud.pop('await_tool', None)")
    lines.append("        await message.reply_text(run_tool(str(_await), text)[:3500])")
    lines.append("        return")
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
    lines.append("        # confirm step: نعم/لا")
    lines.append("        if str(key) == 'confirm':")
    lines.append("            ans = (text or '').strip().lower()")
    lines.append("            yes = ans in ('نعم', 'yes', 'y', 'ok', 'تمام', 'أكد', 'تاكيد', '1')")
    lines.append("            no = ans in ('لا', 'no', 'n', 'الغاء', 'إلغاء', '0')")
    lines.append("            if not yes and not no:")
    lines.append("                await message.reply_text('للتأكيد اكتب نعم — للإلغاء اكتب لا')")
    lines.append("                return")
    lines.append("            if no:")
    lines.append("                ud.clear()")
    lines.append("                await message.reply_text('تم إلغاء الطلب')")
    lines.append("                return")
    lines.append("            data['confirm'] = 'yes'")
    lines.append("            data['status'] = 'confirmed'")
    lines.append("        else:")
    lines.append("            data[key] = text")
    lines.append("        # numeric helpers")
    lines.append("        if str(key) == 'quantity':")
    lines.append("            try:")
    lines.append("                qv = int(str(text).strip())")
    lines.append("                if qv <= 0:")
    lines.append("                    raise ValueError('qty')")
    lines.append("                data['quantity'] = qv")
    lines.append("            except Exception:")
    lines.append("                await message.reply_text('أرسل كمية صحيحة (رقم أكبر من صفر)')")
    lines.append("                return")
    lines.append("        if str(key) not in ('confirm', 'quantity') and str(text).replace('.', '', 1).isdigit():")
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
    lines.append("        if 'status' not in payload:")
    lines.append("            payload['status'] = payload.get('status') or 'open'")
    lines.append("        # Persist collected text into per-user memory list (structural, any domain)")
    lines.append("        app_data = context.application.bot_data")
    lines.append("        bucket = app_data.setdefault('records', {})")
    lines.append("        mine = bucket.setdefault(str(uid), [])")
    lines.append("        title = str(payload.get('title') or payload.get('task_name') or payload.get('text') or text or '').strip()")
    lines.append("        if title and str(flow_id) not in ('order',):")
    lines.append("            mine.append({'title': title, 'status': 'open', 'flow': str(flow_id)})")
    lines.append("            msgs.append('تم الحفظ: ' + title)")

    lines.append("        if False:  # defensive pack removed")
    lines.append("            target = str(payload.get('domain') or payload.get('url') or payload.get('target') or title or text or '').strip()")
    lines.append("            if target:")
    lines.append("                try:")
    lines.append("                    from app.tools import run_evidenced_checks")
    lines.append("                    msgs.append(run_evidenced_checks(target))")
    lines.append("                except Exception as _te:")
    lines.append("                    msgs.append('tool_error:' + str(_te))")
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

    lines.append("    # Quick actions from list-style keyboards")
    lines.append("    if data.startswith('done:') or data.startswith('del:'):")
    lines.append("        app_data = context.application.bot_data")
    lines.append("        all_tasks = app_data.setdefault('records', {})")
    lines.append("        uid = str(update.effective_user.id if update.effective_user else 0)")
    lines.append("        mine = all_tasks.setdefault(str(uid), [])")
    lines.append("        active = [t for t in mine if (t.get('status') or 'open') != 'done']")
    lines.append("        try:")
    lines.append("            idx = int(data.split(':', 1)[1])")
    lines.append("        except Exception:")
    lines.append("            idx = -1")
    lines.append("        if 0 <= idx < len(active):")
    lines.append("            if data.startswith('done:'):")
    lines.append("                active[idx]['status'] = 'done'")
    lines.append("                if query.message is not None:")
    lines.append("                    await query.edit_message_text('تم إنهاء المهمة ✅')")
    lines.append("            else:")
    lines.append("                # hard delete from mine")
    lines.append("                victim = active[idx]")
    lines.append("                try:")
    lines.append("                    mine.remove(victim)")
    lines.append("                except ValueError:")
    lines.append("                    victim['status'] = 'deleted'")
    lines.append("                if query.message is not None:")
    lines.append("                    await query.edit_message_text('تم حذف المهمة 🗑')")
    lines.append("        else:")
    lines.append("            if query.message is not None:")
    lines.append("                await query.edit_message_text('المهمة غير موجودة')")
    lines.append("        return")
    lines.append("    # Route button → command/flow (structural mapping, no domain packs)")
    lines.append("    target_cmd = BUTTON_TO_CMD.get(data) or \"\"")
    lines.append("    if not target_cmd and data.startswith(\"cmd:\"):")
    lines.append("        target_cmd = data[4:]")
    lines.append("    if target_cmd and target_cmd in FLOWS and FLOWS[target_cmd]:")
    lines.append("        if query.message is not None:")
    lines.append("            await _start_flow(query.message, context, target_cmd)")
    lines.append("        return")
    lines.append("    if target_cmd:")
    lines.append("        # Deep route: capability commands execute API path; else soft acknowledge")
    lines.append("        caps = list(CAPABILITY_BY_CMD.get(target_cmd) or [])")
    lines.append("        if caps:")
    lines.append("            await _run_capabilities(update, context, caps, [])")
    lines.append("            return")
    lines.append("        if target_cmd.startswith(\"show_\") or target_cmd in (\"menu\", \"list\"):")
    lines.append("            if query.message is not None:")
    lines.append("                kb = main_keyboard()")
    lines.append("                await query.message.reply_text(CALLBACK_LABELS.get(data) or target_cmd, reply_markup=kb)")
    lines.append("            return")
    lines.append("        msg = f\"استخدم /{target_cmd} أو أكمل من هنا.\"")
    lines.append("        ruled = logic.apply_rules({\"choice\": data, \"text\": data, \"intent\": target_cmd, **dict(context.user_data.get(\"collected\") or {})})")
    lines.append("        context.user_data[\"collected\"] = ruled")
    lines.append("        if ruled.get(\"_messages\"):")
    lines.append("            msg = \" | \".join(str(m) for m in ruled[\"_messages\"][:5])")
    lines.append("        if query.message is not None:")
    lines.append("            await query.edit_message_text(msg)")
    lines.append("        return")
    lines.append("    # Unmapped button labels: acknowledge only (no forced domain order flow)")
    lines.append("    label = CALLBACK_LABELS.get(data) or data")
    lines.append("    if label and not target_cmd:")
    lines.append("        if query.message is not None:")
    lines.append("            await query.edit_message_text('تم اختيار: ' + str(label))")
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
        "    def store_for(self, entity: str):",
        "        key = (entity or '').strip().lower().replace(' ', '_')",
        "        if not key:",
        "            return getattr(self, 'primary_store', None)",
        "        # exact / plural-insensitive attribute lookup",
        "        for name, val in self.__dict__.items():",
        "            if name in ('primary_store',):",
        "                continue",
        "            n = name.lower()",
        "            if n == key or n.rstrip('s') == key.rstrip('s') or key in n or n in key:",
        "                return val",
        "        return getattr(self, 'primary_store', None)",
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
        "    telegram_bot_token: str = Field(default=\"\", description=\"Required only to run the bot process\")",
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
    _JUNK = {'ssl','tls','example','information','com','http','https','www','order','pin','records','status','certificate','headers','check'}
    commands = [c for c in commands if getattr(c, 'name', '') not in _JUNK]
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
        "    settings = get_settings()\n""    if not (settings.telegram_bot_token or \"\").strip():\n""        raise SystemExit(\"Set TELEGRAM_BOT_TOKEN in .env to run the bot\")\n"
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
    _dt = set(getattr(inf, "defensive_tools", None) or [])
    if _dt & {"mx", "spf", "dmarc"}:
        reqs.append("dnspython>=2.4.0")
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
    w("app/tools.py", emit_tools_module(inf))
    w("app/services.py", _emit_services_module(inf))
    w("app/handlers.py", _emit_handlers_module(inf))
    w("app/container.py", _emit_container(inf))
    w("app/config.py", _emit_config(inf))
    w("main.py", _emit_main(inf))
    w("requirements.txt", _emit_requirements(inf))
    w(".env.example", _emit_env(inf))
    return written
