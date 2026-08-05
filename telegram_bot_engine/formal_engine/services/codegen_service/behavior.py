"""Structural behavior emitters — ProgramContract only (no domain packs)."""
from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from ...schemas.program_contract import ProgramContract


def _ident(name: str) -> str:
    s = re.sub(r"[^a-zA-Z0-9_]", "_", (name or "").strip())
    if not s or s[0].isdigit():
        s = "n_" + s
    return s.lower()[:48]


def _py(s: Any) -> str:
    return repr(s)


def snake_entity(name: str) -> str:
    s = re.sub(r"(?<!^)(?=[A-Z])", "_", (name or "").strip()).lower()
    return re.sub(r"[^a-z0-9_]", "_", s)[:40] or "item"


def resolve_service_for_command(
    cmd: str,
    service_names: list[str],
    entity_names: list[str],
) -> str | None:
    cmd = (cmd or "").lower()
    services = [s.lower() for s in service_names]
    if cmd in services:
        return cmd
    for s in services:
        if s and (s in cmd or cmd in s or cmd.rstrip("s") == s or s.rstrip("s") == cmd):
            return s
    entities = [snake_entity(e) for e in entity_names]
    for e in entities:
        if not e or e not in services:
            continue
        if e in cmd or cmd in e or cmd.rstrip("s") == e or e.rstrip("s") == cmd:
            return e
        if any(tok in cmd for tok in (e, e.rstrip("s")) if len(tok) > 2):
            return e
    non_meta = [s for s in services if s not in ("storage", "task_queue", "payments", "notifications")]
    if len(non_meta) == 1:
        return non_meta[0]
    if len(services) == 1:
        return services[0]
    return None


def primary_entity_snake(c: "ProgramContract") -> str | None:
    for e in c.entities or []:
        sn = snake_entity(e.name)
        if sn and sn != "user":
            return sn
    if c.entities:
        return snake_entity(c.entities[0].name)
    return None


def emit_rich_service(name: str, responsibility: str = "") -> str:
    cls = "".join(p.capitalize() for p in _ident(name).split("_") if p) + "Service"
    return (
        f'"""Service {name} — {responsibility or name}."""\n'
        "from __future__ import annotations\n"
        "from typing import Any\n\n\n"
        f"class {cls}:\n"
        "    def __init__(self, repo: Any = None) -> None:\n"
        "        self._repo = repo\n\n"
        "    async def handle(self, user_id: int = 0, args: list | None = None, payload: dict | None = None) -> str:\n"
        "        args = list(args or [])\n"
        "        payload = dict(payload or {})\n"
        "        if self._repo is None:\n"
        f'            return "{name}: ok (no store)"\n'
        '        if payload and hasattr(self._repo, "create"):\n'
        "            data = dict(payload)\n"
        '            data.setdefault("user_id", user_id)\n'
        "            oid = await self._repo.create(**data)\n"
        '            return f"تم الإنشاء: {oid}"\n'
        '        if args and hasattr(self._repo, "get"):\n'
        "            row = await self._repo.get(str(args[0]))\n"
        "            if row is None:\n"
        '                return "غير موجود."\n'
        "            return str(row)\n"
        '        if user_id and hasattr(self._repo, "list_by_user"):\n'
        "            rows = await self._repo.list_by_user(user_id)\n"
        "            if rows:\n"
        '                return "\\n".join(str(r) for r in rows[:30])\n'
        '        if hasattr(self._repo, "list_all"):\n'
        "            rows = await self._repo.list_all()\n"
        "            if not rows:\n"
        '                return "لا بيانات."\n'
        '            return "\\n".join(str(r) for r in rows[:30])\n'
        f'        return "{name}: ok"\n\n'
        "    async def ensure_user(self, telegram_id: int, username: str | None = None, full_name: str = \"\") -> None:\n"
        '        if self._repo is not None and hasattr(self._repo, "ensure"):\n'
        "            await self._repo.ensure(telegram_id, username, full_name)\n"
    )


def emit_messages_ptb(c: "ProgramContract") -> str:
    states = list(c.conversation_states or [])
    if not states:
        return (
            '"""Text fallback."""\n'
            "from __future__ import annotations\n"
            "from telegram import Update\n"
            "from telegram.ext import ContextTypes\n\n\n"
            "async def message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:\n"
            "    message = update.effective_message\n"
            "    if message is None or not message.text:\n"
            "        return\n"
            '    await message.reply_text("استخدم /start أو الأزرار.")\n'
        )
    first = states[0].name
    primary = primary_entity_snake(c) or "item"
    next_lit = ",\n".join(
        f"    {_py(s.name)}: {_py(s.next_state) if s.next_state else None}" for s in states
    )
    prompt_lit = ",\n".join(
        f"    {_py(s.name)}: {_py(s.prompt or s.name)}" for s in states
    )
    return (
        '"""Conversation runner — states from ProgramContract only."""\n'
        "from __future__ import annotations\n"
        "from telegram import Update\n"
        "from telegram.ext import ContextTypes\n"
        "from app.container import get_container\n\n"
        "_NEXT: dict[str, str | None] = {\n"
        f"{next_lit}\n"
        "}\n"
        "_PROMPTS: dict[str, str] = {\n"
        f"{prompt_lit}\n"
        "}\n"
        f"_FIRST = {_py(first)}\n"
        f"_PRIMARY_SVC = {_py(primary)}\n\n\n"
        "async def message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:\n"
        "    message = update.effective_message\n"
        "    if message is None or not message.text:\n"
        "        return\n"
        "    ud = context.user_data\n"
        '    state = ud.get("state")\n'
        "    if not state:\n"
        '        await message.reply_text("استخدم /start أو الأزرار.")\n'
        "        return\n"
        '    collected = list(ud.get("collected") or [])\n'
        "    collected.append(message.text.strip())\n"
        '    ud["collected"] = collected\n'
        "    nxt = _NEXT.get(state)\n"
        "    if nxt:\n"
        '        ud["state"] = nxt\n'
        "        await message.reply_text(_PROMPTS.get(nxt) or nxt)\n"
        "        return\n"
        '    ud["state"] = None\n'
        '    payload = {f"field_{i+1}": v for i, v in enumerate(collected)}\n'
        '    payload["raw"] = " | ".join(collected)\n'
        "    container = get_container()\n"
        "    svc = getattr(container, _PRIMARY_SVC, None)\n"
        "    user = update.effective_user\n"
        "    uid = user.id if user is not None else 0\n"
        '    if svc is not None and hasattr(svc, "handle"):\n'
        "        result = await svc.handle(user_id=uid, args=[], payload=payload)\n"
        "        await message.reply_text(result if isinstance(result, str) else str(result))\n"
        '        ud["collected"] = []\n'
        "        return\n"
        '    await message.reply_text("تم حفظ المدخلات: " + " | ".join(collected))\n'
        '    ud["collected"] = []\n'
    )


def emit_messages_aiogram(c: "ProgramContract") -> str:
    states = list(c.conversation_states or [])
    if not states:
        return (
            '"""Text fallback — aiogram."""\n'
            "from __future__ import annotations\n"
            "from aiogram.types import Message\n\n\n"
            "async def message_handler(message: Message) -> None:\n"
            "    if not message.text:\n"
            "        return\n"
            '    await message.answer("استخدم /start أو الأزرار.")\n'
        )
    first = states[0].name
    primary = primary_entity_snake(c) or "item"
    next_lit = ",\n".join(
        f"    {_py(s.name)}: {_py(s.next_state) if s.next_state else None}" for s in states
    )
    prompt_lit = ",\n".join(
        f"    {_py(s.name)}: {_py(s.prompt or s.name)}" for s in states
    )
    return (
        '"""Conversation runner — aiogram — states from contract."""\n'
        "from __future__ import annotations\n"
        "from aiogram.types import Message\n"
        "from app.container import get_container\n\n"
        "_USER_STATE: dict[int, str | None] = {}\n"
        "_USER_DATA: dict[int, list[str]] = {}\n"
        "_NEXT: dict[str, str | None] = {\n"
        f"{next_lit}\n"
        "}\n"
        "_PROMPTS: dict[str, str] = {\n"
        f"{prompt_lit}\n"
        "}\n"
        f"_FIRST = {_py(first)}\n"
        f"_PRIMARY_SVC = {_py(primary)}\n\n\n"
        "def start_flow(user_id: int) -> str:\n"
        "    _USER_STATE[user_id] = _FIRST\n"
        "    _USER_DATA[user_id] = []\n"
        "    prompt = _PROMPTS.get(_FIRST)\n"
        "    if prompt is None:\n"
        "        return str(_FIRST)\n"
        "    return str(prompt)\n\n\n"
        "async def message_handler(message: Message) -> None:\n"
        "    if not message.text:\n"
        "        return\n"
        "    user = message.from_user\n"
        "    uid = user.id if user is not None else 0\n"
        "    state = _USER_STATE.get(uid)\n"
        "    if not state:\n"
        '        await message.answer("استخدم /start أو الأزرار.")\n'
        "        return\n"
        "    collected = list(_USER_DATA.get(uid) or [])\n"
        "    collected.append(message.text.strip())\n"
        "    _USER_DATA[uid] = collected\n"
        "    nxt = _NEXT.get(state)\n"
        "    if nxt:\n"
        "        _USER_STATE[uid] = nxt\n"
        "        await message.answer(_PROMPTS.get(nxt) or nxt)\n"
        "        return\n"
        "    _USER_STATE[uid] = None\n"
        '    payload = {f"field_{i+1}": v for i, v in enumerate(collected)}\n'
        '    payload["raw"] = " | ".join(collected)\n'
        "    container = get_container()\n"
        "    svc = getattr(container, _PRIMARY_SVC, None)\n"
        '    if svc is not None and hasattr(svc, "handle"):\n'
        "        result = await svc.handle(user_id=uid, args=[], payload=payload)\n"
        "        await message.answer(result if isinstance(result, str) else str(result))\n"
        "        _USER_DATA[uid] = []\n"
        "        return\n"
        '    await message.answer("تم حفظ المدخلات: " + " | ".join(collected))\n'
        "    _USER_DATA[uid] = []\n"
    )


def emit_cmd_aiogram(
    name: str,
    description: str,
    admin_only: bool,
    service_attr: str | None,
) -> str:
    fn = f"{_ident(name)}_handler"
    desc = description or name
    svc = service_attr or name
    lines = [
        f'"""Command /{name} — {desc} (aiogram)."""',
        "from __future__ import annotations",
        "from aiogram.types import Message",
        "from app.container import get_container",
    ]
    if admin_only or name == "admin":
        lines.append("from app.config import get_settings")
    lines += ["", "", f"async def {fn}(message: Message) -> None:"]
    if admin_only or name == "admin":
        lines += [
            "    settings = get_settings()",
            "    user = message.from_user",
            "    if user is None:",
            "        return",
            "    if settings.admin_ids and user.id not in settings.admin_ids:",
            '        await message.answer("هذا الأمر للإدارة فقط.")',
            "        return",
        ]
    lines += [
        "    container = get_container()",
        '    args = (message.text or "").split()[1:]',
        "    user = message.from_user",
        "    uid = user.id if user is not None else 0",
        f"    svc = getattr(container, {_py(svc)}, None)",
        '    if svc is not None and hasattr(svc, "handle"):',
        "        result = await svc.handle(user_id=uid, args=args)",
        "        await message.answer(result if isinstance(result, str) else str(result))",
        "        return",
        f"    await message.answer({_py('/' + name + ' — ' + desc)})",
        "",
    ]
    return "\n".join(lines) + "\n"


def emit_callbacks_aiogram(c: "ProgramContract") -> str:
    has_states = bool(c.conversation_states)
    cases = []
    for b in c.buttons or []:
        if has_states:
            cases.append(
                f"    if data == {_py(b.callback_id)}:\n"
                "        user = callback.from_user\n"
                "        uid = user.id if user is not None else 0\n"
                "        from app.handlers.messages import start_flow\n"
                "        prompt = start_flow(uid)\n"
                "        if callback.message:\n"
                "            await callback.message.answer(prompt)\n"
                "        return\n"
            )
        else:
            cases.append(
                f"    if data == {_py(b.callback_id)}:\n"
                f"        if callback.message:\n"
                f"            await callback.message.edit_text({_py(b.label)})\n"
                f"        return\n"
            )
    body = "\n".join(cases) if cases else "    pass\n"
    return (
        '"""Callbacks — aiogram — wired to conversation flow when states exist."""\n'
        "from __future__ import annotations\n"
        "from aiogram.types import CallbackQuery\n\n\n"
        "async def callback_handler(callback: CallbackQuery) -> None:\n"
        "    await callback.answer()\n"
        '    data = callback.data or ""\n'
        + body
        + "    if callback.message:\n"
        '        await callback.message.edit_text(f"Action: {data}")\n'
    )
